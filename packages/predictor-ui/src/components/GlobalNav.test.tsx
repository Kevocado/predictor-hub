import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { GlobalNav, type NavEntry } from "./GlobalNav";

const entries: NavEntry[] = [
  { id: "pl", label: "Premier League", href: "https://pl.example" },
  { id: "nfl", label: "NFL", href: "https://sports.example/?sport=nfl" },
  { id: "cfb", label: "College football", href: "https://sports.example/?sport=cfb" },
  { id: "nba", label: "NBA", href: "https://nba.example" },
  { id: "f1", label: "F1", href: "https://f1.example" },
  { id: "paper", label: "Paper Trading", href: "https://example/paper.html" },
];

describe("GlobalNav", () => {
  it("renders one nav with an anchor per entry", () => {
    render(<GlobalNav entries={entries} activeId="nba" />);
    const nav = screen.getByRole("navigation", { name: "Sports" });
    expect(nav.querySelectorAll("a")).toHaveLength(entries.length);
  });

  it("marks the active entry with aria-current=page", () => {
    render(<GlobalNav entries={entries} activeId="nfl" />);
    expect(screen.getByRole("link", { name: "NFL" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "NBA" })).not.toHaveAttribute("aria-current");
  });

  it("contains its own overflow instead of widening the page", () => {
    render(<GlobalNav entries={entries} activeId={null} />);
    const scroller = screen.getByTestId("global-nav-scroller");
    expect(scroller.className).toMatch(/overflow-x-auto/);
  });

  it("lets the nav shrink below its entries' combined width (the page must not scroll sideways)", () => {
    render(<GlobalNav entries={entries} activeId={null} />);
    expect(screen.getByRole("navigation")).toHaveClass("min-w-0", "max-w-full");
  });

  it("does not render the fade when not overflowing", () => {
    render(<GlobalNav entries={entries} activeId={null} />);
    expect(screen.queryByTestId("global-nav-fade")).toBeNull();
  });
});