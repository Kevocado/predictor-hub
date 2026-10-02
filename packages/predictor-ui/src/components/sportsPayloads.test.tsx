/**
 * The real `Sports_Predictor` rows, through the real component.
 *
 * **Why this file exists.** Rule 4 ("draw a row's `detail`") shipped with a
 * harness fixture as its only evidence, and the fixture was wrong about the
 * world. It used heading `"Rush yds — projections, not probabilities"` with
 * detail `"Rush yds"`, where the two tokenise to the same words — so the
 * de-duplication worked in the test and would not have worked on the page.
 *
 * These are the rows `Sports_Predictor` `origin/main` actually builds
 * (`src/lib/picksPanel.ts`), copied verbatim from that file rather than
 * invented, because the whole value of this file is that the strings are the
 * ones a real adapter passes:
 *
 *   :79  { position: "QB",      market: "passing_yards",  category: "QB passing yards",     detail: "Pass yds" }
 *   :80  { position: "RB",      market: "rushing_yards",  category: "RB rushing yards",     detail: "Rush yds" }
 *   :81  { position: ["WR","TE"],market: "receiving_yards",category: "WR/TE receiving yards",detail: "Rec yds"  }
 *   :273 { detail: tdCategory, kind: "probability" }        — the heading's own text
 *   :324 { detail: `${side} ${line}`, kind: "probability" }  — the call
 *
 * The first three rows each ABBREVIATE their own heading — `{pass, yds}` and
 * `{qb, passing, yards}` share no token — so a token comparison called them new
 * and drew them, and each is `kind: "projection"`, so the drawn text read
 * `Pass yds · model call`: the heading restated, on the most visible line of
 * the row, described as a call it is not.
 *
 * Nothing here reaches a site repo, the network, or a fixture: it is a string
 * table plus the component. If `Sports_Predictor` changes these strings, this
 * file is the thing that should be looked at, and it is checked by name rather
 * than by hash so the failure says which row moved.
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { PicksList, DEFAULT_DETAIL_LABEL, type PickRow } from "./PicksList";

/** The panel's real heading text, from the constants in that same file. */
const NFL_TD_CATEGORY = "Rush or receiving TD";
const CFB_TD_CATEGORY = "Anytime TD";
const NFL_QB_PASSING_TD_CATEGORY = "QB passing TDs";

type Spec = { category: string; detail: string; kind: PickRow["kind"]; value: number; source: string };

/** `positionCategories()` verbatim, and the two yardage kinds it builds. */
const YARDAGE: Spec[] = [
  { category: "QB passing yards", detail: "Pass yds", kind: "projection", value: 284, source: "picksPanel.ts:79" },
  { category: "RB rushing yards", detail: "Rush yds", kind: "projection", value: 96, source: "picksPanel.ts:80" },
  { category: "WR/TE receiving yards", detail: "Rec yds", kind: "projection", value: 62, source: "picksPanel.ts:81" },
];

/** The two TD categories (:273) and the QB passing-TD call (:324). */
const CALLS: Spec[] = [
  { category: NFL_TD_CATEGORY, detail: NFL_TD_CATEGORY, kind: "probability", value: 0.41, source: "picksPanel.ts:273" },
  { category: CFB_TD_CATEGORY, detail: CFB_TD_CATEGORY, kind: "probability", value: 0.38, source: "picksPanel.ts:273" },
  { category: NFL_QB_PASSING_TD_CATEGORY, detail: "Over 2.5", kind: "probability", value: 0.64, source: "picksPanel.ts:324" },
];

const rowFor = (spec: Spec, i = 0): PickRow => ({
  key: `${spec.category}:${i}`,
  name: "A. Rodgers",
  team: "PIT",
  detail: spec.detail,
  value: spec.value,
  kind: spec.kind,
});

/** Render one real category and hand back its single row. */
function renderSpec(spec: Spec) {
  const { container } = render(
    <PicksList categories={[{ category: spec.category, rows: [rowFor(spec)] }]} />,
  );
  return { container, row: screen.getByTestId("picks-row") };
}

describe("Sports_Predictor's real rows · DEFECT 1 — an abbreviated restatement", () => {
  // "Pass yds" under "QB passing yards" shares NO token with it. A rule that
  // only compared words called this new information and drew it.
  it.each(YARDAGE)("$source: draws no detail for $detail under $category", (spec) => {
    const { container, row } = renderSpec(spec);
    expect(screen.queryByTestId("picks-detail"), `${spec.detail} was drawn under "${spec.category}"`).not.toBeInTheDocument();
    expect(container.textContent).not.toContain(spec.detail);
    // Still the player, team and the prediction — the row the reader had before.
    // The figure is read off the spec, not typed: a literal here would fail on
    // the third row and pass on the first two.
    expect(row.textContent).toBe(`1A. Rodgers · PIT${spec.value.toFixed(1)}`);
  });

  it("would have drawn it: the abbreviation defeats a token comparison", () => {
    // The defect stated as an executable fact rather than a claim, so the test
    // above is not just asserting a wish. This is the pre-fix rule.
    const tokens = (t: string) => t.toLowerCase().split(/[^a-z0-9.]+/).filter(Boolean);
    const shared = tokens("Pass yds").filter((w) => tokens("QB passing yards").includes(w));
    expect(shared).toEqual([]);
  });

  it("covers all three abbreviated yardage categories in one panel, as the site does", () => {
    render(
      <PicksList
        categories={YARDAGE.map((spec, i) => ({ category: spec.category, rows: [rowFor(spec, i)] }))}
      />,
    );
    expect(screen.getAllByTestId("picks-category-heading")).toHaveLength(3);
    expect(screen.queryByTestId("picks-detail")).not.toBeInTheDocument();
    for (const spec of YARDAGE) expect(screen.getByTestId("picks-list").textContent).not.toContain(spec.detail);
  });
});

describe("Sports_Predictor's real rows · DEFECT 2 — a false call qualifier", () => {
  it.each(YARDAGE)("$source: labels no projection as a call", (spec) => {
    // "Pass yds · model call" — a yardage estimate described as a call, on the
    // most visible line of the row. The qualifier must not exist here at all.
    const { container } = renderSpec(spec);
    expect(container.textContent).not.toContain(DEFAULT_DETAIL_LABEL);
    expect(container.textContent).not.toContain("model call");
  });

  it.each(YARDAGE)("$source: ignores a detailLabel the caller supplied on a projection", (spec) => {
    // Even an explicit one. A qualifier is a claim that the row states a call,
    // and a projection states a magnitude, so the component does not draw it
    // rather than trusting the caller not to ask.
    const { container } = render(
      <PicksList
        categories={[{
          category: spec.category,
          rows: [{ ...rowFor(spec), detailLabel: "model line" }],
        }]}
      />,
    );
    expect(screen.queryByTestId("picks-detail")).not.toBeInTheDocument();
    expect(container.textContent).not.toContain("model line");
  });

  it("no projection row in the whole panel carries a call qualifier", () => {
    render(
      <PicksList
        categories={YARDAGE.map((spec, i) => ({
          category: spec.category,
          rows: [rowFor(spec, i), { ...rowFor(spec, i + 1), key: "b", name: "J. Allen", detailLabel: "model call" }],
        }))}
      />,
    );
    expect(screen.queryByTestId("picks-detail")).not.toBeInTheDocument();
    expect(screen.getByTestId("picks-list").textContent).not.toContain("model");
  });
});

describe("Sports_Predictor's real rows · the requirement still holds", () => {
  // The thing this whole change exists for. If any fix above ever suppresses
  // this row, NFL's QB passing-TD category is a bare percentage again.
  it("still draws the call and its qualifier on the QB passing-TD row", () => {
    const spec = CALLS[2];
    const { row } = renderSpec(spec);
    const detail = within(row).getByTestId("picks-detail");
    expect(detail.textContent).toBe(`Over 2.5 · ${DEFAULT_DETAIL_LABEL}`);
    expect(within(row).getByTestId("picks-value")).toHaveTextContent("64%");
    expect(within(row).getByTestId("picks-bar")).toHaveStyle({ width: "64%" });
  });

  it("still draws both sides of the market — Over and Under are different calls", () => {
    render(
      <PicksList
        categories={[{
          category: NFL_QB_PASSING_TD_CATEGORY,
          rows: [
            rowFor(CALLS[2], 0),
            { ...rowFor(CALLS[2], 1), key: "b", name: "J. Burrow", detail: "Under 1.5", value: 0.53 },
          ],
        }]}
      />,
    );
    expect(screen.getAllByTestId("picks-detail").map((d) => d.firstChild?.textContent)).toEqual([
      "Over 2.5",
      "Under 1.5",
    ]);
  });

  it.each([NFL_TD_CATEGORY, CFB_TD_CATEGORY])(
    "draws no detail for the %s category, whose detail IS its heading",
    (category) => {
      // These two are `kind: "probability"`, so the kind gate cannot suppress
      // them: the token half of the rule is what does, and it is still needed.
      const spec = CALLS.find((s) => s.category === category)!;
      expect(spec.kind).toBe("probability");
      renderSpec(spec);
      expect(screen.queryByTestId("picks-detail")).not.toBeInTheDocument();
    },
  );

  it("draws the call and nothing else when a projection heading would have matched", () => {
    // One panel, the real yardage categories and the real call side by side:
    // the gate is per row, so suppressing three projection rows costs the
    // probability row nothing.
    render(
      <PicksList
        categories={[...YARDAGE, CALLS[2]].map((spec, i) => ({
          category: spec.category,
          rows: [rowFor(spec, i)],
        }))}
      />,
    );
    expect(screen.getAllByTestId("picks-detail")).toHaveLength(1);
    expect(screen.getByTestId("picks-detail").textContent).toBe("Over 2.5 · model call");
  });
});