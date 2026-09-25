import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { StatusBadge } from "./StatusBadge";
import { TeamChip } from "./TeamChip";
import { StatTile } from "./StatTile";
import { EmptyState, ErrorState, Skeleton } from "./States";

describe("StatusBadge", () => {
  it.each([
    ["next", "Next up"],
    ["live", "Live"],
    ["called", "Called it ✓"],
    ["missed", "Missed ✗"],
    ["nopick", "No pick yet"],
    ["rebuilt", "Rebuilt after kickoff"],
  ] as const)("%s reads '%s' (never colour alone)", (status, words) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByText(words)).toBeInTheDocument();
  });
});

describe("TeamChip", () => {
  it("shows the code, names the team for assistive tech, and picks readable ink", () => {
    render(<TeamChip code="LSU" name="LSU Tigers" color="#F5B301" />);
    const chip = screen.getByLabelText("LSU Tigers");
    expect(chip).toHaveTextContent("LSU");
    expect(chip).toHaveStyle({ color: "#0B0D10" });
  });
  it("uses light ink on a dark team colour", () => {
    render(<TeamChip code="NYG" name="New York Giants" color="#0B2265" />);
    expect(screen.getByLabelText("New York Giants")).toHaveStyle({ color: "#F3F5F8" });
  });
  it("falls back to a neutral chip without a colour", () => {
    render(<TeamChip code="MIA" />);
    expect(screen.getByText("MIA")).toBeInTheDocument();
  });
});

describe("StatTile", () => {
  it("shows label, value and an optional note", () => {
    render(<StatTile label="Picks the winner" value="64%" sub="Sep 18 model" />);
    expect(screen.getByText("Picks the winner")).toBeInTheDocument();
    expect(screen.getByText("64%")).toBeInTheDocument();
    expect(screen.getByText("Sep 18 model")).toBeInTheDocument();
  });
});

describe("States", () => {
  it("Skeleton names what is loading and is announced", () => {
    render(<Skeleton label="Loading picks…" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading picks…");
  });
  it("EmptyState offers a next step", () => {
    const go = vi.fn();
    render(<EmptyState message="No games this week." action={{ label: "Go to next week", onClick: go }} />);
    expect(screen.getByRole("status")).toHaveTextContent("No games this week.");
    fireEvent.click(screen.getByRole("button", { name: "Go to next week" }));
    expect(go).toHaveBeenCalledOnce();
  });
  it("ErrorState is an alert with Try again", () => {
    const retry = vi.fn();
    render(<ErrorState message="We couldn't load this week's games." onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("We couldn't load this week's games.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});

describe("TeamChip outline", () => {
  it("keeps a visible edge when the team colour is close to the panel", () => {
    render(<TeamChip code="CLE" name="Cleveland Browns" color="#311D00" />);
    expect(screen.getByLabelText("Cleveland Browns").className).toMatch(/ring-1/);
  });
});

describe("StatusBadge in F1", () => {
  it("words a rebuilt pick around the session", () => {
    render(<StatusBadge status="rebuilt" moment="the session" />);
    expect(screen.getByText("Rebuilt after the session")).toBeInTheDocument();
  });
});
