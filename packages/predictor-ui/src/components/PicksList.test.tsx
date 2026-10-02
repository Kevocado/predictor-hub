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
import {
  PicksList,
  DEFAULT_DETAIL_LABEL,
  OutPlayerInRankingError,
  RowKindMismatchError,
  detailAddsToHeading,
  type PickRow,
} from "./PicksList";

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

/* ---------------------------------------------------------------------------
 * Rule 4 — the row's `detail` renders only when it says something the category
 * heading above it does not already say. The rationale, and the two readings of
 * "always" that were rejected, are in `detailAddsToHeading` above; these tests
 * are the rule's edge, because a rule that only ever has one case is not a rule.
 * ------------------------------------------------------------------------- */

describe("the row's own detail · when it adds a word the heading does not carry", () => {
  /** The target case: NFL's QB passing-TD rows, where the call is the detail
   *  and the probability is the value. */
  const passing = (over: Partial<PickRow> = {}): PickRow => ({
    key: "rodgers",
    name: "A. Rodgers",
    team: "PIT",
    detail: "Over 2.5",
    detailLabel: "model line",
    value: 0.64,
    kind: "probability",
    ...over,
  });

  it("renders the call, so the row is a line and a probability and not a bare percentage", () => {
    // The requirement, verbatim: `Over 2.5 · 64%`. Before this rule the row was
    // "A. Rodgers · PIT" and "64%", and 64% of WHAT is not a thing a reader can act on.
    render(<PicksList categories={[{ category: "QB passing TDs", rows: [passing()] }]} />);
    const row = screen.getByTestId("picks-row");
    const detail = within(row).getByTestId("picks-detail");
    expect(detail.textContent).toContain("Over 2.5");
    expect(within(row).getByTestId("picks-value")).toHaveTextContent("64%");
    // The bar is still that probability's bar: adding a line does not rescale it.
    expect(within(row).getByTestId("picks-bar")).toHaveStyle({ width: "64%" });
  });

  it("renders every called row of the category, each with its own line", () => {
    // Three QBs, three different lines — the reason the detail is per row and
    // not a heading suffix. A list where every row shared one line would not
    // need the field at all, and this is the shape that proves it earns it.
    render(
      <PicksList
        categories={[{
          category: "QB passing TDs",
          rows: [
            passing({ key: "a", name: "A. Rodgers", detail: "Over 2.5", value: 0.64 }),
            passing({ key: "b", name: "J. Allen", detail: "Under 1.5", value: 0.58 }),
            passing({ key: "c", name: "J. Hurts", detail: "Over 1.5", value: 0.52 }),
          ],
        }]}
      />,
    );
    expect(screen.getAllByTestId("picks-detail").map((d) => d.firstChild?.textContent)).toEqual([
      "Over 2.5",
      "Under 1.5",
      "Over 1.5",
    ]);
  });

  it("renders nothing extra where the detail duplicates the heading", () => {
    // The cost this rule exists to avoid. NFL, CFB and NBA rows carry
    // `detail: "Pass yds"` under a `"Pass yds"` heading today; printing it three
    // times per card is the duplication, not the fix.
    render(
      <PicksList
        categories={[{
          category: "Pass yds",
          rows: [
            proj({ key: "a", name: "A. Rodgers", value: 284, detail: "Pass yds" }),
            proj({ key: "b", name: "B. Robinson", value: 96, detail: "Pass yds" }),
          ],
        }]}
      />,
    );
    expect(screen.queryByTestId("picks-detail")).not.toBeInTheDocument();
    for (const row of screen.getAllByTestId("picks-row")) {
      // Still the player and the prediction, and nothing else.
      expect(row.textContent).not.toContain("Pass yds");
    }
    expect(screen.getAllByTestId("picks-row")[0].textContent).toBe("1A. Rodgers284.0");
  });

  it("suppresses a detail the heading already carries INSIDE a longer heading", () => {
    // Equality would not do this, and this is the case that proves it: the
    // harness builds the heading "Rush yds — projections, not probabilities",
    // so `"Rush yds" !== heading` and every projection card in the family would
    // print its heading three more times.
    render(
      <PicksList
        categories={[{
          category: "Rush yds — projections, not probabilities",
          rows: [proj({ key: "b", name: "B. Robinson", value: 96, detail: "Rush yds" })],
        }]}
      />,
    );
    expect(screen.queryByTestId("picks-detail")).not.toBeInTheDocument();
  });

  it("renders nothing at all for an empty list", () => {
    const { container } = render(<PicksList categories={[]} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId("picks-list")).not.toBeInTheDocument();
    expect(screen.queryByTestId("picks-detail")).not.toBeInTheDocument();
  });

  it("renders no detail for a category that has no rows", () => {
    // "No pick yet" stays the whole answer. A qualifier under it would be a
    // line for nobody.
    render(<PicksList categories={[{ category: "QB passing TDs", rows: [] }]} />);
    expect(screen.getByText("No pick yet")).toBeInTheDocument();
    expect(screen.queryByTestId("picks-detail")).not.toBeInTheDocument();
  });

  it("renders nothing for an empty detail, rather than an empty chip", () => {
    render(
      <PicksList
        categories={[{
          category: "QB passing TDs",
          rows: [passing({ detail: "" }), passing({ key: "b", name: "J. Allen", detail: "   " })],
        }]}
      />,
    );
    expect(screen.queryByTestId("picks-detail")).not.toBeInTheDocument();
  });
});

describe("the rendered detail must never read as a sportsbook line", () => {
  const row = (over: Partial<PickRow> = {}): PickRow => ({
    key: "a",
    name: "A. Rodgers",
    detail: "Over 2.5",
    value: 0.64,
    kind: "probability",
    ...over,
  });

  it("qualifies the detail with visible words, not a tooltip", () => {
    // A `title` is invisible on the phone this is mostly read on and is not
    // reliably announced from a span, so the provenance has to be in the text
    // the reader can see. Asserted on `textContent`, so a title-only
    // implementation fails here.
    render(<PicksList categories={[{ category: "QB passing TDs", rows: [row()] }]} />);
    const detail = screen.getByTestId("picks-detail");
    expect(detail.textContent).toBe(`Over 2.5 · ${DEFAULT_DETAIL_LABEL}`);
  });

  it("defaults to a noun the component can vouch for, whatever the caller passed", () => {
    expect(DEFAULT_DETAIL_LABEL).toBe("model call");
    render(<PicksList categories={[{ category: "QB passing TDs", rows: [row()] }]} />);
    // `value` is documented as the model's own number, and the detail is the
    // caller's words for what it is picking: "model call" is true of both.
    expect(screen.getByTestId("picks-detail").textContent).toContain("model call");
  });

  it("takes the caller's own noun, which is how Sports_Predictor says \"model line\"", () => {
    // The plan's wording for the QB passing-TD market. It has to be the
    // caller's to choose: the shared component cannot know that one detail is
    // a line and another is not.
    render(
      <PicksList
        categories={[{ category: "QB passing TDs", rows: [row({ detailLabel: "model line" })] }]}
      />,
    );
    expect(screen.getByTestId("picks-detail").textContent).toBe("Over 2.5 · model line");
  });

  it("never lets the qualifier turn a suppressed detail into a rendered one", () => {
    render(
      <PicksList
        categories={[{
          category: "Over 2.5",
          rows: [row({ detail: "Over 2.5", detailLabel: "model line" })],
        }]}
      />,
    );
    expect(screen.queryByTestId("picks-detail")).not.toBeInTheDocument();
  });

  it("says none of the banned words in the qualifier, in any of its three forms", () => {
    for (const detailLabel of [undefined, "model line", "model call"]) {
      const { unmount } = render(
        <PicksList
          categories={[{ category: "QB passing TDs", rows: [row({ detailLabel })] }]}
        />,
      );
      const text = (screen.getByTestId("picks-detail").textContent ?? "").toLowerCase();
      for (const word of ["lock", "guaranteed", "best bet", "edge", "value"]) {
        expect(text, `"${word}" in "${text}"`).not.toContain(word);
      }
      unmount();
    }
  });
});

describe("the detail rule cannot break the two guards", () => {
  it("REFUSES a yardage figure on a row that also carries a call", () => {
    // Rule 4 adds a slot to the row; it must not add a way past the kind guard.
    expect(() =>
      render(
        <PicksList
          categories={[{ category: "QB passing TDs", rows: [{
            key: "a", name: "A. Rodgers", detail: "Over 2.5", value: 284, kind: "probability",
          }] }]}
        />,
      ),
    ).toThrow(RowKindMismatchError);
  });

  it("still names the detail in the refusal, so the message points at the row", () => {
    // `detail` was already the second thing the message carried; rule 4 made it
    // visible on the page and must not have cost it its job in the error.
    expect(() =>
      render(
        <PicksList
          categories={[{ category: "QB passing TDs", rows: [{
            key: "a", name: "A. Rodgers", detail: "Over 2.5", value: 284, kind: "probability",
          }] }]}
        />,
      ),
    ).toThrow(/is a Over 2\.5 probability row/);
  });

  it("REFUSES an out player on a row that also carries a call", () => {
    expect(() =>
      render(
        <PicksList
          categories={[{ category: "QB passing TDs", rows: [{
            key: "j", name: "A. Rodgers", detail: "Over 2.5", value: 0.64, kind: "probability", out: true,
          }] }]}
        />,
      ),
    ).toThrow(OutPlayerInRankingError);
  });
});

describe("detailAddsToHeading · the rule itself, edge by edge", () => {
  it("renders a call whose words the heading does not carry", () => {
    expect(detailAddsToHeading("Over 2.5", "QB passing TDs")).toBe(true);
  });

  it("suppresses an exact restatement", () => {
    expect(detailAddsToHeading("Pass yds", "Pass yds")).toBe(false);
  });

  it("suppresses a restatement inside a longer heading, ignoring case", () => {
    expect(detailAddsToHeading("Rush yds", "Rush yds — projections, not probabilities")).toBe(false);
    expect(detailAddsToHeading("RUSH YDS", "rush yds")).toBe(false);
  });

  it("treats a number with its decimal point as one token", () => {
    // "Over 2.5" against "Over 2 5", or against "2.5" alone: a dot split into
    // its own token would let "Over 2.5" through under a heading that already
    // says it, which is the duplication the rule exists to stop.
    expect(detailAddsToHeading("2.5", "Over 2.5")).toBe(false);
    expect(detailAddsToHeading("Over 2.5", "Over 2.5 — model lines")).toBe(false);
  });

  it("renders nothing for a detail with no words in it", () => {
    for (const detail of ["", "   ", "—", "· ·"]) {
      expect(detailAddsToHeading(detail, "QB passing TDs"), JSON.stringify(detail)).toBe(false);
    }
  });

  it("renders the detail under a heading that does not mention its own category", () => {
    // The caller's inconsistency, said out loud rather than dropped. A detail
    // of "Pass yds" under "Rush yds" is a bug in the adapter; hiding it would
    // make the bug invisible, which is what the kind guard exists to prevent.
    expect(detailAddsToHeading("Pass yds", "Rush yds")).toBe(true);
  });

  it("renders a detail that is only partly covered, on the uncovered word alone", () => {
    expect(detailAddsToHeading("Rush yds over 74.5", "Rush yds")).toBe(true);
  });

  it("drops a detail made entirely of words the heading already uses — the stated loss", () => {
    // "The heading is what the reader navigates by, and `value` separates two
    // rows under one heading." Pinned so a future widening of the rule is a
    // deliberate act rather than a side effect of a regex change.
    expect(detailAddsToHeading("passing", "QB passing TDs")).toBe(false);
  });
});