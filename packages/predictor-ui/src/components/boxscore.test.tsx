import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { BoxScore, type BoxScoreColumn, type BoxScoreGroup, type BoxScoreRow } from "./BoxScore";

const columns: BoxScoreColumn[] = [
  { key: "yds", label: "Yds", align: "right" },
  { key: "pct", label: "TD %", align: "right" },
];

function row(over: Partial<BoxScoreRow> = {}): BoxScoreRow {
  return {
    key: "r1", name: "Test Player", position: "QB", team: "MIA",
    order: 0, isStarter: true, values: [250, 0.62], ...over,
  };
}

function group(
  rows: BoxScoreRow[],
  subtotals: BoxScoreGroup["subtotals"] = null,
): BoxScoreGroup {
  return { position: "QB", rows, subtotals };
}

describe("BoxScore — the three starter states", () => {
  it("renders a known game with no projected-order note", () => {
    render(
      <BoxScore
        columns={columns}
        groups={[group([row({ key: "a", isStarter: true }), row({ key: "b", isStarter: false })])]}
        title="Predicted box score"
      />,
    );
    expect(screen.queryByTestId("box-score-projected-note")).toBeNull();
    expect(screen.getByText(/starters listed before bench/i)).toBeTruthy();
  });

  it("renders the visible 'Projected order' note when no row has starter data", () => {
    render(
      <BoxScore
        columns={columns}
        groups={[group([row({ key: "a", isStarter: null }), row({ key: "b", isStarter: null })])]}
        title="Predicted box score"
      />,
    );
    const note = screen.getByTestId("box-score-projected-note");
    // Visible, not a title attribute, not a colour. A sport without depth-chart
    // data must never be mistaken for one that has it.
    expect(note.textContent).toMatch(/projected order/i);
    expect(note.textContent).toMatch(/no depth-chart feed/i);
    expect(screen.getByRole("table")).toBeTruthy();
  });

  it("keeps a known header when only ONE row lacks starter data", () => {
    // A single null row must not flip the whole table to "projected" -- the
    // header would then lie about the rows that do have a real starter.
    render(
      <BoxScore
        columns={columns}
        groups={[group([row({ key: "a", isStarter: true }), row({ key: "b", isStarter: null })])]}
        title="Predicted box score"
      />,
    );
    expect(screen.queryByTestId("box-score-projected-note")).toBeNull();
    // and the null row is still labelled, per row, for a screen reader.
    const rows = screen.getAllByTestId("box-score-row");
    expect(rows[0].getAttribute("data-starter")).toBe("starter");
    expect(rows[1].getAttribute("data-starter")).toBe("projected");
    expect(rows[1].textContent).toMatch(/projected order, no depth-chart data/i);
  });

  it("marks a bench row distinctly from a starter", () => {
    render(
      <BoxScore
        columns={columns}
        groups={[group([row({ key: "a", isStarter: true }), row({ key: "b", isStarter: false })])]}
      />,
    );
    const rows = screen.getAllByTestId("box-score-row");
    expect(rows.map((r) => r.getAttribute("data-starter"))).toEqual(["starter", "bench"]);
  });
});

describe("BoxScore — null values", () => {
  it("renders an em-dash for a null value, never a zero", () => {
    // A null is "no prediction", not "predicted zero". Rendering 0.0 would be a
    // fabricated number on a public page.
    render(<BoxScore columns={columns} groups={[group([row({ values: [null, 0.62] })])]} />);
    const cell = within(screen.getAllByTestId("box-score-row")[0]).getAllByRole("cell")[0];
    expect(cell.textContent).toBe("—");
    expect(cell.textContent).not.toBe("0.0");
  });

  it("renders an em-dash in a subtotal for a null too", () => {
    render(
      <BoxScore
        columns={columns}
        groups={[group([row()], [{ label: "MIA total", values: [null, 0.62] }])]}
      />,
    );
    expect(within(screen.getByTestId("box-score-subtotal")).getAllByRole("cell")[0].textContent).toBe("—");
  });

  it("drops a trailing decimal on an integer and keeps one otherwise", () => {
    render(<BoxScore columns={columns} groups={[group([row({ values: [250, 0.62] })])]} />);
    const cells = within(screen.getAllByTestId("box-score-row")[0]).getAllByRole("cell");
    expect(cells[0].textContent).toBe("250");
    expect(cells[1].textContent).toBe("0.6");
  });
});

describe("BoxScore — ordering is the caller's, not the component's", () => {
  it("renders rows in the order given, even when the data is out of order", () => {
    // This is the whole point of presentational: a team must be able to render
    // its players in depth-chart order, which is not alphabetical and not by
    // points. If the component reordered, that would be impossible.
    const rows = [
      row({ key: "z", name: "Zeta", order: 99 }),
      row({ key: "a", name: "Alpha", order: 1 }),
      row({ key: "m", name: "Mu", order: 50 }),
    ];
    render(<BoxScore columns={columns} groups={[group(rows)]} />);
    const names = screen.getAllByTestId("box-score-row").map((r) => r.textContent);
    expect(names[0]).toMatch(/Zeta/);
    expect(names[1]).toMatch(/Alpha/);
    expect(names[2]).toMatch(/Mu/);
  });

  it("renders each group in its own tbody with a position header", () => {
    render(
      <BoxScore
        columns={columns}
        groups={[
          { position: "QB", rows: [row({ key: "q" })] },
          { position: "WR", rows: [row({ key: "w", position: "WR" })] },
        ]}
      />,
    );
    const bodies = screen.getAllByRole("rowgroup");
    // thead + one tbody per group
    expect(bodies.length).toBe(3);
    expect(within(bodies[1]).getByText("QB")).toBeTruthy();
    expect(within(bodies[2]).getByText("WR")).toBeTruthy();
  });
});

describe("BoxScore — table semantics", () => {
  it("is a real table with scoped headers", () => {
    render(<BoxScore columns={columns} groups={[group([row()])]} title="Predicted" />);
    expect(screen.getByRole("table").tagName).toBe("TABLE");
    for (const label of ["Player", "Yds", "TD %"]) {
      expect(screen.getByRole("columnheader", { name: label })).toBeTruthy();
    }
    expect(screen.getByRole("rowheader", { name: /Test Player/ })).toBeTruthy();
  });

  it("gives a cell its describe() text for a screen reader", () => {
    const describe = vi.fn((value: number | null, r: BoxScoreRow) => `${r.name} rush yards ${value ?? "none"}`);
    render(
      <BoxScore
        columns={[{ key: "yds", label: "Yds", describe }]}
        groups={[group([row({ key: "a", name: "Alpha", values: [250] })])]}
      />,
    );
    const cell = screen.getByRole("cell", { name: "Alpha rush yards 250" });
    expect(cell).toBeTruthy();
    expect(describe).toHaveBeenCalled();
  });

  it("uses a colgroup header for each position", () => {
    render(<BoxScore columns={columns} groups={[{ position: "QB", rows: [row()] }]} />);
    expect(screen.getByRole("columnheader", { name: "QB" }).getAttribute("scope")).toBe("colgroup");
  });
});

describe("BoxScore — subtotals and the projected score", () => {
  it("renders a subtotal row per team, aligned to the columns", () => {
    render(
      <BoxScore
        columns={columns}
        groups={[
          group([row()], [
            { label: "MIA total", values: [250, 0.62] },
            { label: "BUF total", values: [180, 0.51] },
          ]),
        ]}
      />,
    );
    const subs = screen.getAllByTestId("box-score-subtotal");
    expect(subs).toHaveLength(2);
    expect(within(subs[0]).getAllByRole("cell").map((c) => c.textContent)).toEqual(["250", "0.6"]);
  });

  it("marks the projected score as strong", () => {
    render(
      <BoxScore
        columns={columns}
        groups={[group([row()], [{ label: "Projected", values: [250, 0.62], strong: true }])]}
      />,
    );
    expect(screen.getByTestId("box-score-subtotal").textContent).toMatch(/Projected/);
  });
});

describe("BoxScore — edges", () => {
  it("renders nothing when there are no rows", () => {
    const { container } = render(<BoxScore columns={columns} groups={[group([])]} />);
    expect(container.querySelector("[data-testid='box-score']")).toBeNull();
  });

  it("emphasises the column the caller nominated", () => {
    render(<BoxScore columns={columns} groups={[group([row({ emphasisIndex: 1 })])]} />);
    const cells = within(screen.getAllByTestId("box-score-row")[0]).getAllByRole("cell");
    expect(cells[1].className).toMatch(/font-semibold/);
    expect(cells[0].className).not.toMatch(/font-semibold/);
  });

  it("names the team beside the player", () => {
    render(<BoxScore columns={columns} groups={[group([row({ name: "Tyreek", team: "MIA" })])]} />);
    expect(screen.getByTestId("box-score-row").textContent).toMatch(/Tyreek/);
    expect(screen.getByTestId("box-score-row").textContent).toMatch(/MIA/);
  });
});

describe("BoxScore — values that are not real numbers", () => {
  it("renders NaN as an em-dash, never as the text NaN", () => {
    // Found while wiring A4: a consumer multiplying a missing probability by
    // 100 produced NaN, which reached a public cell as the literal string
    // "NaN". A component that renders it is helping a caller ship garbage.
    render(
      <BoxScore
        columns={[{ key: "td", label: "TD %" }]}
        groups={[group([row({ values: [NaN] })])]}
      />,
    );
    const cell = within(screen.getAllByTestId("box-score-row")[0]).getByRole("cell");
    expect(cell.textContent).toBe("—");
    expect(cell.textContent).not.toMatch(/NaN/);
  });

  it("treats Infinity as absent too", () => {
    render(
      <BoxScore
        columns={[{ key: "td", label: "TD %" }]}
        groups={[group([row({ values: [Infinity] })])]}
      />,
    );
    expect(within(screen.getAllByTestId("box-score-row")[0]).getByRole("cell").textContent).toBe("—");
  });

  it("keeps a real number, so the guard did not swallow everything", () => {
    render(
      <BoxScore
        columns={[{ key: "yds", label: "Yds" }]}
        groups={[group([row({ values: [42.5] })])]}
      />,
    );
    expect(within(screen.getAllByTestId("box-score-row")[0]).getByRole("cell").textContent).toBe("42.5");
  });
});
