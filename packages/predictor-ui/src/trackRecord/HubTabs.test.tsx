/**
 * The shared tab bar. Five sites drew their own: NBA with `aria-current`
 * buttons, Sports with `aria-pressed`, PL with strings, F1 with `display:none`
 * panels. At 375px they clipped. This one is a real tablist with roving focus,
 * and it contains its own overflow so the page never scrolls sideways.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { HubTabs, type HubTab } from "./HubTabs";

const TABS: HubTab[] = [
  { id: "games", label: "Games" },
  { id: "teams", label: "Teams" },
  { id: "players", label: "Players" },
  { id: "rankings", label: "Rankings" },
  { id: "track-record", label: "Track record" },
];

function Harness() {
  const [active, setActive] = useState("games");
  return (
    <HubTabs
      tabs={TABS}
      active={active}
      onChange={setActive}
      label="Sections"
      panels={Object.fromEntries(TABS.map((t) => [t.id, <p key={t.id}>Panel {t.id}</p>]))}
    />
  );
}

describe("HubTabs", () => {
  it("is a labelled tablist with a tab per section and one tabpanel", () => {
    render(<Harness />);
    const list = screen.getByRole("tablist", { name: "Sections" });
    expect(within(list).getAllByRole("tab")).toHaveLength(TABS.length);
    expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
  });

  it("marks the active tab and points the panel at it", () => {
    render(<Harness />);
    const active = screen.getByRole("tab", { name: "Games" });
    expect(active).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Teams" })).toHaveAttribute("aria-selected", "false");
    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAttribute("aria-labelledby", active.id);
    expect(panel).toHaveTextContent("Panel games");
  });

  it("keeps a roving tabindex: only the active tab is in the tab order", () => {
    render(<Harness />);
    expect(screen.getByRole("tab", { name: "Games" })).toHaveAttribute("tabindex", "0");
    for (const name of ["Teams", "Players", "Rankings", "Track record"]) {
      expect(screen.getByRole("tab", { name }), name).toHaveAttribute("tabindex", "-1");
    }
  });

  it("moves selection and focus with the arrow keys", async () => {
    render(<Harness />);
    screen.getByRole("tab", { name: "Games" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Teams" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Teams" })).toHaveFocus();
  });

  it("wraps at both ends and jumps with Home and End", async () => {
    render(<Harness />);
    screen.getByRole("tab", { name: "Games" }).focus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "Track record" })).toHaveFocus();
    await userEvent.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Games" })).toHaveFocus();
    await userEvent.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Track record" })).toHaveFocus();
  });

  it("selects on click and swaps the panel", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("tab", { name: "Players" }));
    expect(screen.getByRole("tab", { name: "Players" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Panel players");
  });
});
