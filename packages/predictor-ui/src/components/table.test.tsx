import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { StatTable, type Column } from "./StatTable";

type R = { team: string; epa: number | null };
const rows: R[] = [{ team: "KC", epa: 0.12 }, { team: "BAL", epa: null }, { team: "MIA", epa: -0.05 }];
const cols: Column<R>[] = [
  { key: "team", label: "Team", value: (r) => r.team },
  { key: "epa", label: "Off EPA/play", value: (r) => r.epa, numeric: true, tooltip: "Expected points added per play" },
];

describe("StatTable", () => {
  it("sorts by a header, missing values last in both directions, and says the sort", () => {
    render(<StatTable rows={rows} columns={cols} rowKey={(r) => r.team} caption="Teams" />);
    const sortBtn = screen.getByRole("button", { name: /Off EPA\/play/ });
    fireEvent.click(sortBtn);
    const names = () => screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0].textContent);
    expect(names()).toEqual(["KC", "MIA", "BAL"]);
    expect(screen.getByRole("columnheader", { name: /Off EPA\/play/ })).toHaveAttribute("aria-sort", "descending");
    fireEvent.click(sortBtn);
    expect(names()).toEqual(["MIA", "KC", "BAL"]);
    expect(screen.getAllByText("—").length).toBe(1);
  });
  it("expands a row's detail with a labelled toggle", () => {
    render(<StatTable rows={rows} columns={cols} rowKey={(r) => r.team} caption="Teams" expand={(r) => <p>Detail {r.team}</p>} />);
    fireEvent.click(screen.getByRole("button", { name: "Show KC details" }));
    expect(screen.getByText("Detail KC")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide KC details" })).toHaveAttribute("aria-expanded", "true");
  });
});
