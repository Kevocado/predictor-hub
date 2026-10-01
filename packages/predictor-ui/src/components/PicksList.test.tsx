/**
 * The eight cases the Phase 2 plan names, in its order, plus the two guards
 * that exist because of what review has already caught:
 *
 *  - a row's `kind` must match its `value`'s range, so a yardage figure can
 *    never render as a probability (the "9600%" defect), and
 *  - an `out` player passed as a row is REFUSED in code, because "removed,
 *    not flagged" has to be enforced by the component rather than by every
 *    caller's discipline.
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { PicksList, OutPlayerInRankingError, RowKindMismatchError, type PickRow } from "./PicksList";

const prob = (over: Partial<PickRow> & Pick<PickRow, "key" | "name" | "value">): PickRow => ({
  detail: "Anytime TD",
  kind: "probability",
  provenance: "model 41% · bucket hits 44% · n=112",
  ...over,
});

const proj = (over: Partial<PickRow> & Pick<PickRow, "key" | "name" | "value">): PickRow => ({
  detail: "Rush yds",
  kind: "projection",
  margin: 18,
  provenance: "MAE 18.0 · n=112",
  ...over,
});

/** How many rows this list actually rendered — the cap under test is on THIS. */
const rowsRendered = (container: HTMLElement) =>
  within(container).getByTestId("picks-category").querySelectorAll('[data-testid="picks-row"]').length;

describe("1 · a heading per category, at most three rows, never padded", () => {
  it("renders the heading for each category, in order", () => {
    render(
      <PicksList
        categories={[
          { category: "Anytime TD", rows: [prob({ key: "a", name: "B. Robinson", value: 0.38 })] },
          { category: "Rush yds", rows: [proj({ key: "b", name: "E. Wilson", value: 41 })] },
        ]}
      />,
    );
    const headings = screen.getAllByTestId("picks-category-heading").map((h) => h.textContent);
    expect(headings).toEqual(["Anytime TD", "Rush yds"]);
  });

  it("a four-row input renders three — the cap is a cap, not a quota to fill", () => {
    const { container } = render(
      <PicksList
        categories={[
          {
            category: "Anytime TD",
            rows: [
              prob({ key: "a", name: "One", value: 0.41 }),
              prob({ key: "b", name: "Two", value: 0.38 }),
              prob({ key: "c", name: "Three", value: 0.24 }),
              prob({ key: "d", name: "Four", value: 0.22 }),
            ],
          },
        ]}
      />,
    );
    expect(rowsRendered(container)).toBe(3);
    expect(screen.getByText("Three")).toBeInTheDocument();
    expect(screen.queryByText("Four")).not.toBeInTheDocument();
  });

  it("a one-row input renders one and is never padded", () => {
    const { container } = render(
      <PicksList
        categories={[
          { category: "Rebounds", rows: [proj({ key: "a", name: "B. Adebayo", value: 10.2, margin: 2.3, detail: "Rebounds" })] },
        ]}
      />,
    );
    expect(rowsRendered(container)).toBe(1);
    // No ghost rows, and no second player invented to make the list look fuller.
    expect(screen.getAllByTestId("picks-row")).toHaveLength(1);
  });
});

describe("2 · a probability row is the player and one percentage, with a thin bar", () => {
  it("shows the percentage and a bar of exactly that share, and nothing else", () => {
    render(<PicksList categories={[{ category: "Anytime TD", rows: [prob({ key: "a", name: "B. Robinson", team: "ATL", value: 0.38 })] }]} />);
    const row = screen.getByTestId("picks-row");
    expect(within(row).getByTestId("picks-value")).toHaveTextContent("38%");
    expect(within(row).getByTestId("picks-bar")).toHaveStyle({ width: "38%" });
    expect(row.textContent).toContain("B. Robinson");
    expect(row.textContent).toContain("ATL");
  });

  it("keeps a tiny probability visible rather than rounding the bar away", () => {
    render(<PicksList categories={[{ category: "Anytime TD", rows: [prob({ key: "a", name: "Edge", value: 0.03 })] }]} />);
    const w = parseFloat((screen.getByTestId("picks-bar") as HTMLElement).style.width);
    expect(w).toBeGreaterThanOrEqual(3);
  });
});

describe("3 · a projection row is the player and one figure, and NEVER a percentage", () => {
  it("shows the figure with no % and no bar", () => {
    const { container } = render(
      <PicksList categories={[{ category: "Rush yds", rows: [proj({ key: "b", name: "B. Robinson", value: 96 })] }]} />,
    );
    const row = screen.getByTestId("picks-row");
    expect(within(row).getByTestId("picks-value")).toHaveTextContent("96.0");
    // The defect this row shape exists to prevent: 96 read as a share.
    expect(row.textContent).not.toContain("%");
    expect(container.querySelector('[data-testid="picks-bar"]')).toBeNull();
  });
});

describe("4 · nothing but the prediction is on a row (Kevin, 2026-10-01)", () => {
  it("renders none of the caller's provenance, record, error or calibration prose", () => {
    const provenance = "raw score, uncalibrated · graded · Brier 0.15 over 346 resolved props · bucket 50-60% scored 60%";
    const { container } = render(
      <PicksList
        categories={[
          { category: "Anytime TD", rows: [prob({ key: "a", name: "A. Rodgers", team: "PIT", value: 0.81, provenance })] },
          { category: "Rush yds", rows: [proj({ key: "b", name: "B. Robinson", value: 96, margin: 18, provenance })] },
        ]}
      />,
    );
    const text = container.textContent ?? "";
    for (const bit of ["uncalibrated", "Brier", "graded", "resolved", "bucket", "MAE", "±", "no error estimate", "projection, not", "the rest of the field"]) {
      expect(text, `row text must not contain "${bit}"`).not.toContain(bit);
    }
  });

  it("numbers the rows 1 to 3 so the ranking reads at a glance", () => {
    render(
      <PicksList
        categories={[{ category: "Anytime TD", rows: [
          prob({ key: "a", name: "One", value: 0.6 }), prob({ key: "b", name: "Two", value: 0.5 }), prob({ key: "c", name: "Three", value: 0.4 }),
        ] }]}
      />,
    );
    expect(screen.getAllByTestId("picks-rank").map((e) => e.textContent)).toEqual(["1", "2", "3"]);
  });
});

describe("5 · an out player passed as a row is REFUSED, not flagged", () => {
  it("throws a named error rather than rendering him in a ranking", () => {
    // "Removed, not flagged" is a rule about what reaches the page. A caller
    // that ignores it must not get a quietly greyed-out row: the component is
    // the last place that can say no.
    expect(() =>
      render(
        <PicksList
          categories={[
            { category: "Anytime TD", rows: [prob({ key: "j", name: "J. Jacobs", value: 0.41, out: true })] },
          ]}
        />,
      ),
    ).toThrow(OutPlayerInRankingError);
  });

  it("names the player, so the failure points at the caller", () => {
    expect(() =>
      render(
        <PicksList
          categories={[
            { category: "Anytime TD", rows: [prob({ key: "j", name: "J. Jacobs", value: 0.41, out: true })] },
          ]}
        />,
      ),
    ).toThrow(/J\. Jacobs/);
  });
});

describe("6 · the out list renders once, below the categories, with source and date", () => {
  it("shows the attribution and never a bar, a tile or a rank position", () => {
    const { container } = render(
      <PicksList
        categories={[{ category: "Anytime TD", rows: [prob({ key: "a", name: "B. Robinson", value: 0.38 })] }]}
        out={[{ name: "J. Jacobs", team: "GB", source: "Official injury report · week 6", dated: "Oct 1, 09:00" }]}
      />,
    );
    const out = screen.getByTestId("picks-out");
    expect(out.textContent).toContain("J. Jacobs");
    expect(out.textContent).toContain("Official injury report · week 6");
    expect(out.textContent).toContain("Oct 1, 09:00");
    // Once, not once per category.
    expect(container.querySelectorAll('[data-testid="picks-out"]')).toHaveLength(1);
    // And BELOW every category: document order, which jsdom can answer.
    // (Geometry cannot — jsdom lays nothing out, so a width assertion here
    // would be measuring nothing. The 390px screenshot is the layout proof.)
    // `out.compareDocumentPosition(category)` returns PRECEDING (bit 2) when the
    // category comes BEFORE out, which is the claim: below the lists.
    expect(
      out.compareDocumentPosition(screen.getByTestId("picks-category")) & Node.DOCUMENT_POSITION_PRECEDING,
    ).toBeTruthy();
    // He is named there and nowhere in a ranking: no bar, no tile, no rank.
    expect(out.querySelector('[data-testid="pbar-fill"]')).toBeNull();
    expect(out.querySelector("[data-testid^='tile-']")).toBeNull();
    expect(screen.getAllByTestId("picks-row")).toHaveLength(1);
    expect(screen.getByTestId("picks-row")).not.toHaveTextContent("J. Jacobs");
  });

  it("renders no out line at all when nobody is out", () => {
    render(<PicksList categories={[{ category: "Anytime TD", rows: [prob({ key: "a", name: "B. Robinson", value: 0.38 })] }]} />);
    expect(screen.queryByTestId("picks-out")).not.toBeInTheDocument();
  });
});

describe("7 · an empty category says so honestly, and never shows a zero", () => {
  it("renders the existing empty-state vocabulary, not a fabricated figure", () => {
    const { container } = render(<PicksList categories={[{ category: "Anytime TD", rows: [] }]} />);
    expect(screen.getByText("Anytime TD")).toBeInTheDocument();
    expect(screen.getByText("No pick yet")).toBeInTheDocument();
    // No bar, no tile, and no "0%" standing in for a figure nobody produced.
    expect(container.querySelector('[data-testid="pbar-fill"]')).toBeNull();
    expect(container.querySelector('[data-testid="tile-pick"]')).toBeNull();
    expect(container.textContent).not.toContain("0%");
  });
});

describe("8 · no row ever renders a banned word", () => {
  // The plan's banned list, passed in as a fixture rather than inlined, so
  // this test fails if the plan's list grows and nobody re-reads it here.
  const BANNED = ["lock", "guaranteed", "best bet", "edge", "value"] as const;

  it("says none of them, on any row, in any state", () => {
    const { container } = render(
      <PicksList
        title="Model's top calls"
        categories={[
          { category: "Anytime TD", rows: [prob({ key: "a", name: "B. Robinson", value: 0.38 })] },
          { category: "Rush yds", rows: [proj({ key: "b", name: "B. Robinson", value: 96 })] },
          { category: "Rebounds", rows: [] },
        ]}
        out={[{ name: "J. Jacobs", source: "Official injury report", dated: "Oct 1" }]}
      />,
    );
    const text = (container.textContent ?? "").toLowerCase();
    for (const word of BANNED) expect(text, `rendered text must not contain "${word}"`).not.toContain(word);
  });
});

describe("the kind guard — a row's visual must match what its number IS", () => {
  it("REFUSES a yardage figure passed as a probability", () => {
    // The exact defect: with one number per player, 96 rush yards rendered as an
    // anytime-TD probability. The bar would have drawn 9600%.
    expect(() =>
      render(<PicksList categories={[{ category: "Anytime TD", rows: [prob({ key: "b", name: "B. Robinson", value: 96 })] }]} />),
    ).toThrow(RowKindMismatchError);
  });

  it("names the range the value broke", () => {
    expect(() =>
      render(<PicksList categories={[{ category: "Anytime TD", rows: [prob({ key: "b", name: "B. Robinson", value: 96 })] }]} />),
    ).toThrow(/probability.*\[0,1\]/);
  });

  it("accepts a projection below 1 — 0.8 steals and 0.6 touchdowns are real projections", () => {
    // A count can legitimately be a fraction. Refusing the closed interval [0,1]
    // threw during render and took the whole list down (CodeRabbit on hub#63). The
    // row's `kind` is passed explicitly, so magnitude is not how a caller's mistake
    // is caught; the adapter that builds the row owns that.
    for (const value of [0, 0.38, 0.8, 1, 1.4]) {
      const { unmount } = render(
        <PicksList categories={[{ category: "Steals", rows: [proj({ key: "s", name: "Wing", value })] }]} />,
      );
      unmount();
    }
  });

  it("still refuses a negative or non-finite projection", () => {
    for (const value of [-1, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(() =>
        render(<PicksList categories={[{ category: "Rush yds", rows: [proj({ key: "a", name: "J. Love", value })] }]} />),
      ).toThrow(RowKindMismatchError);
    }
  });

  it("accepts the boundaries a real model produces: 0 and 1 are probabilities", () => {
    for (const value of [0, 0.005, 0.995, 1]) {
      const { unmount } = render(
        <PicksList categories={[{ category: "Anytime TD", rows: [prob({ key: "a", name: "Edge", value })] }]} />,
      );
      unmount();
    }
  });
});