import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { StickyStatTable, type StickySection } from "./StickyStatTable";
import { TeamSwitch, TeamToggle } from "./TeamSwitch";

// Real-shaped NBA rows: a long hyphen-free name, a suffix name, a missing stat.
const columns = [
  { key: "pts", label: "PTS" },
  { key: "reb", label: "REB" },
  { key: "ast", label: "AST" },
];
const home: StickySection[] = [
  {
    rows: [
      { key: "gian", header: "Giannis Antetokounmpo", cells: [31.4, 11.8, 5.6] },
      { key: "lill", header: "Damian Lillard", cells: [24.1, null, 7] },
      { key: "bobi", header: "Bobby Portis Jr.", cells: [12, 8.2, Number.NaN] },
    ],
  },
];
const away: StickySection[] = [
  { rows: [{ key: "luka", header: "Luka Dončić", cells: [29, 8.8, 8.1] }] },
];

describe("StickyStatTable", () => {
  it("keeps a long player name whole, in the sticky first cell", () => {
    render(<StickyStatTable columns={columns} sections={home} caption="Bucks" />);
    const cell = screen.getByText("Giannis Antetokounmpo");
    expect(cell.textContent).toBe("Giannis Antetokounmpo");
    const th = cell.closest("th")!;
    expect(th.getAttribute("scope")).toBe("row");
    expect(th.className).toMatch(/\bsticky\b/);
    expect(th.className).toMatch(/\bleft-0\b/);
    // Opaque, so scrolled stats never show through the pinned name.
    expect(th.className).toMatch(/\bbg-pr-/);
    // A fixed width that wraps long names rather than clipping them.
    expect(th.style.width).toBe("10rem");
    expect(th.className).not.toMatch(/truncate|text-ellipsis/);
  });

  it("puts the stat columns inside a focusable, labelled scroll container", () => {
    render(<StickyStatTable columns={columns} sections={home} caption="Bucks" />);
    const scroller = screen.getByRole("region", { name: "Box score, scroll sideways for more stats" });
    expect(scroller.getAttribute("tabindex")).toBe("0");
    expect(scroller.className).toMatch(/overflow-x-auto|overflow-auto/);
    expect(within(scroller).getByRole("table")).toBeTruthy();
    expect(within(scroller).getByRole("columnheader", { name: "PTS" })).toBeTruthy();
  });

  it("pins the headers and the corner cell", () => {
    render(<StickyStatTable columns={columns} sections={home} caption="Bucks" />);
    const pts = screen.getByRole("columnheader", { name: "PTS" });
    expect(pts.className).toMatch(/\bsticky\b/);
    expect(pts.className).toMatch(/\btop-0\b/);
    expect(pts.className).toMatch(/whitespace-nowrap/);
    const corner = screen.getByRole("columnheader", { name: "Player" });
    expect(corner.className).toMatch(/\bsticky\b.*\bleft-0\b|\bleft-0\b.*\bsticky\b/);
  });

  it("right-aligns numbers with tabular numerals and shows an em dash for anything absent", () => {
    render(<StickyStatTable columns={columns} sections={home} caption="Bucks" />);
    const row = screen.getByText("Damian Lillard").closest("tr")!;
    const cells = within(row).getAllByRole("cell");
    expect(cells.map((c) => c.textContent)).toEqual(["24.1", "—", "7"]);
    expect(cells[0].className).toMatch(/text-right/);
    expect(cells[0].className).toMatch(/tabular-nums/);
    // NaN is "no value", never the literal text "NaN".
    const portis = within(screen.getByText("Bobby Portis Jr.").closest("tr")!).getAllByRole("cell");
    expect(portis[2].textContent).toBe("—");
  });

  it("renders totals last and sticky-left too", () => {
    render(
      <StickyStatTable
        columns={columns}
        sections={home}
        footer={[{ key: "t", header: "Total", cells: [67.5, 20, 12.6], total: true }]}
        caption="Bucks"
      />,
    );
    const rows = screen.getAllByRole("row");
    const last = rows[rows.length - 1];
    const th = within(last).getByRole("rowheader", { name: "Total" });
    expect(th.className).toMatch(/\bsticky\b/);
  });

  it("shows a one-line message, and no table, when there are no rows", () => {
    render(<StickyStatTable columns={columns} sections={[{ rows: [] }]} caption="Bucks" empty="No box score for Bucks yet" />);
    expect(screen.getByText("No box score for Bucks yet")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("marks the first column as pinned only once the table has scrolled sideways", () => {
    render(<StickyStatTable columns={columns} sections={home} caption="Bucks" />);
    const scroller = screen.getByRole("region");
    const th = screen.getByText("Damian Lillard").closest("th")!;
    expect(th.getAttribute("data-pinned")).toBe("false");
    scroller.scrollLeft = 40;
    fireEvent.scroll(scroller);
    expect(th.getAttribute("data-pinned")).toBe("true");
  });
});

describe("TeamSwitch", () => {
  const teams = [
    { key: "MIL", label: "MIL" },
    { key: "DAL", label: "DAL" },
  ];
  const byTeam: Record<string, StickySection[]> = { MIL: home, DAL: away };
  const ui = () => (
    <TeamSwitch teams={teams} label="Team box score">
      {(key) => <StickyStatTable columns={columns} sections={byTeam[key]} caption={key} />}
    </TeamSwitch>
  );

  it("defaults to the first (home) team and shows one team at a time", () => {
    render(ui());
    expect(screen.getByText("Giannis Antetokounmpo")).toBeTruthy();
    expect(screen.queryByText("Luka Dončić")).toBeNull();
    expect(screen.getAllByRole("table")).toHaveLength(1);
    const group = screen.getByRole("group", { name: "Team box score" });
    const [mil, dal] = within(group).getAllByRole("button");
    expect(mil.getAttribute("aria-pressed")).toBe("true");
    expect(dal.getAttribute("aria-pressed")).toBe("false");
  });

  it("swaps the rows when the other team is picked", () => {
    render(ui());
    fireEvent.click(screen.getByRole("button", { name: "DAL" }));
    expect(screen.getByText("Luka Dončić")).toBeTruthy();
    expect(screen.queryByText("Giannis Antetokounmpo")).toBeNull();
    expect(screen.getByRole("button", { name: "DAL" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("TeamToggle is controlled", () => {
    let picked = "";
    render(<TeamToggle teams={teams} value="DAL" onChange={(k) => (picked = k)} label="Team" />);
    expect(screen.getByRole("button", { name: "DAL" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "MIL" }));
    expect(picked).toBe("MIL");
  });
});
