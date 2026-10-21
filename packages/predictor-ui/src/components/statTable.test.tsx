import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { StatTable, type Column } from "./StatTable";

interface Row {
  name: string;
  n: number;
}

const rows: Row[] = [
  { name: "one", n: 1 },
  { name: "two", n: 2 },
  { name: "three", n: 3 },
  { name: "four", n: 4 },
];

const columns: Column<Row>[] = [
  { key: "name", label: "Name", value: (r) => r.name },
  { key: "n", label: "N", value: (r) => r.n, numeric: true },
];

function renderTable(over: { separators?: { after: string; label: string }[] } = {}) {
  return render(
    <StatTable
      rows={rows}
      columns={columns}
      rowKey={(r) => r.name}
      caption="A table"
      initialSort={{ key: "n", dir: "asc" }}
      {...over}
    />,
  );
}

describe("StatTable separators", () => {
  it("draws a labelled rule after the row it names", () => {
    renderTable({ separators: [{ after: "two", label: "Play-in (7-10)" }] });

    const separator = screen.getByTestId("table-separator");
    expect(separator).toHaveTextContent("Play-in (7-10)");
  });

  it("draws the rule BETWEEN the rows, after the one it names", () => {
    renderTable({ separators: [{ after: "two", label: "Play-in (7-10)" }] });

    const bodyRows = within(screen.getByRole("table")).getAllByRole("row");
    // The header, then "one", "two", the rule, "three", "four".
    expect(bodyRows).toHaveLength(6);
    expect(bodyRows[3]).toHaveAttribute("data-testid", "table-separator");
    expect(bodyRows[2]).toHaveTextContent("two");
    expect(bodyRows[4]).toHaveTextContent("three");
  });

  it("draws no rule when it is not asked for one", () => {
    renderTable();

    expect(screen.queryByTestId("table-separator")).toBeNull();
  });

  it("draws a rule for each separator it is given", () => {
    renderTable({
      separators: [
        { after: "one", label: "Play-in (7-10)" },
        { after: "three", label: "Out (11+)" },
      ],
    });

    const separators = screen.getAllByTestId("table-separator");
    expect(separators).toHaveLength(2);
    expect(separators[0]).toHaveTextContent("Play-in (7-10)");
    expect(separators[1]).toHaveTextContent("Out (11+)");
  });

  it("ignores a separator that names a row the table does not have", () => {
    renderTable({ separators: [{ after: "nobody", label: "Nowhere" }] });

    expect(screen.queryByTestId("table-separator")).toBeNull();
  });
});
