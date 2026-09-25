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
    // Named from its visible content (WCAG 2.5.3), so nothing on the card is hidden from screen readers.
    expect(card).not.toHaveAttribute("aria-label");
    expect(card).toHaveAccessibleName(/Tottenham.*2–3.*Aston Villa.*Pick: Aston Villa win · 38%/);
    expect(card.querySelector("div")).toBeNull();
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

describe("readability of team colours on the dark panel", () => {
  it("swaps a team colour that would vanish on the panel for a visible neutral", () => {
    const { container } = render(<ProbabilityBar segments={[{ label: "PIT", prob: 0.45, color: "#FFB612" }, { label: "CLE", prob: 0.55, color: "#311D00" }]} />);
    const fills = container.querySelectorAll<HTMLElement>("[data-testid='pbar-fill']");
    expect(fills[0].style.backgroundColor).toBe("rgb(255, 182, 18)");
    expect(fills[1].style.backgroundColor).not.toBe("rgb(49, 29, 0)");
  });
});

describe("MatchCard without a pick", () => {
  it("has no empty pick section", () => {
    const { container, rerender } = render(<MatchCard {...base} status="nopick" />);
    expect(container.querySelector("[data-testid='pick-section']")).toBeNull();
    rerender(<MatchCard {...base} pick={{ label: "Aston Villa win", prob: 0.38 }} />);
    expect(container.querySelector("[data-testid='pick-section']")).not.toBeNull();
  });
});

describe("fallback fills", () => {
  it("gives home, draw and away three different fills when no team colours are known", () => {
    const { container } = render(<ProbabilityBar segments={[{ label: "Home", prob: 0.4 }, { label: "Draw", prob: 0.3 }, { label: "Away", prob: 0.3 }]} />);
    const fills = [...container.querySelectorAll<HTMLElement>("[data-testid='pbar-fill']")].map((f) => f.style.backgroundColor);
    expect(new Set(fills).size).toBe(3);
  });
});

describe("MatchCard review fixes", () => {
  it("reads the date and sport meta to screen readers too", () => {
    render(<MatchCard {...base} status="next" when="Sun 4 Oct · 12:00 PM CDT" meta="BAL −2.5 · Total 46.5" pick={{ label: "Ravens", prob: 0.62 }} />);
    expect(screen.getByRole("button")).toHaveAccessibleName(/Sun 4 Oct · 12:00 PM CDT.*BAL −2\.5 · Total 46\.5/);
  });
  it("always says 'No pick yet' when there is no pick, whatever the status", () => {
    render(<MatchCard {...base} status="next" />);
    expect(screen.getByText("No pick yet")).toBeInTheDocument();
  });
});

describe("MatchCard without a status", () => {
  it("shows no status words for an upcoming game that is not next, but still says when there is no pick", () => {
    render(<MatchCard left={base.left} right={base.right} centre="15:00" onOpen={() => {}} />);
    expect(screen.queryByText(/Next up|Live|Called it|Missed|Rebuilt after kickoff/)).toBeNull();
    expect(screen.getByText("No pick yet")).toBeInTheDocument();
  });
});
