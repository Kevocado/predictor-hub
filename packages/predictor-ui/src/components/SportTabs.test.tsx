import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { SportTabs } from "./SportTabs";
import type { SportTab } from "./SportTabs";

const TABS: SportTab[] = [
  { id: "games", label: "Games" },
  { id: "teams", label: "Teams" },
  { id: "players", label: "Players" },
  { id: "standings", label: "Standings" },
  { id: "track-record", label: "Track record" },
  { id: "calibration", label: "Calibration" },
  { id: "model", label: "Model" },
  { id: "power-rankings", label: "Power rankings" },
];

function Harness() {
  const [active, setActive] = useState("games");
  return <SportTabs tabs={TABS} active={active} onChange={setActive} label="Pages" panels={Object.fromEntries(TABS.map((t) => [t.id, <p key={t.id}>Panel {t.id}</p>]))} />;
}

describe("SportTabs", () => {
  it("is a labelled tablist with one tab per section and one tabpanel", () => {
    render(<Harness />);
    const list = screen.getByRole("tablist", { name: "Pages" });
    expect(within(list).getAllByRole("tab")).toHaveLength(TABS.length);
    expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
  });

  it("marks the active tab with aria-selected", () => {
    render(<Harness />);
    expect(screen.getByRole("tab", { name: "Games" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Teams" })).toHaveAttribute("aria-selected", "false");
  });

  it("keeps a roving tabindex", () => {
    render(<Harness />);
    expect(screen.getByRole("tab", { name: "Games" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: "Teams" })).toHaveAttribute("tabindex", "-1");
  });

  it("moves selection and focus with arrow keys", async () => {
    const userEvent = (await import("@testing-library/user-event")).default;
    render(<Harness />);
    screen.getByRole("tab", { name: "Games" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Teams" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Teams" })).toHaveFocus();
  });

  it("contains its own overflow instead of widening the page", () => {
    render(<div style={{ width: 375 }}><SportTabs tabs={TABS} active="games" onChange={() => {}} /></div>);
    const list = screen.getByRole("tablist");
    expect(list.className).toMatch(/overflow-x-auto/);
  });

  it("does not render the fade when not overflowing", () => {
    render(<SportTabs tabs={TABS} active="games" onChange={() => {}} />);
    expect(screen.queryByTestId("hub-tabs-fade")).toBeNull();
  });

  it("calls onChange on click", () => {
    const onTab = vi.fn();
    render(<SportTabs tabs={TABS} active="games" onChange={onTab} />);
    fireEvent.click(screen.getByRole("tab", { name: "Teams" }));
    expect(onTab).toHaveBeenCalledWith("teams");
  });
});