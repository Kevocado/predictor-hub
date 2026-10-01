/**
 * The component against the harness fixture — the two halves that used to be
 * separate are now pinned together in one place.
 *
 * `harness/fixture.ts` already range-checks every row against its category's
 * kind; the guard here is the SAME check, run by the real component, on rows
 * built from those real players. A disagreement between the fixture's kind and
 * the component's kind would otherwise be invisible until a site shipped it.
 *
 * Note on scope: the harness is not shipped, so nothing here is imported by a
 * site and nothing in `src/` depends on this file.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PicksList, RowKindMismatchError, type PickRow } from "./PicksList";
import { LISTS, CATEGORY_KIND, PLAYERS, ranked, valueOf, type Category } from "../../harness/fixture";

/** The fixture's own ranked players, as rows the component accepts. */
function rowsFor(category: Category): PickRow[] {
  return ranked(category).map((p) => ({
    key: `${p.key}:${category}`,
    name: p.name,
    team: p.team,
    detail: category,
    value: valueOf(p, category),
    kind: CATEGORY_KIND[category],
    provenance: CATEGORY_KIND[category] === "probability" ? `bucket hits n=${p.bucket?.n ?? 0}` : "projection, not a probability",
    ...(CATEGORY_KIND[category] === "projection" ? { margin: p.mae?.[category] } : {}),
  }));
}

const ALL = () => LISTS.map(({ category }) => ({ category, rows: rowsFor(category) }));

describe("the harness fixture, through the real component", () => {
  it("every fixture list renders — no row of any category is refused", () => {
    render(<PicksList categories={ALL()} />);
    expect(screen.getAllByTestId("picks-category-heading").map((h) => h.textContent)).toEqual(
      LISTS.map(({ category }) => category),
    );
    // One row per ranked player, per category, and no more.
    const expected = LISTS.reduce((n, { category }) => n + ranked(category).length, 0);
    expect(screen.getAllByTestId("picks-row")).toHaveLength(expected);
  });

  it("the out player is absent from every rendered row", () => {
    render(<PicksList categories={ALL()} out={[{ name: PLAYERS.jacobs.name, team: PLAYERS.jacobs.team, source: "official injury report", dated: "Sep 30" }]} />);
    for (const row of screen.getAllByTestId("picks-row")) {
      expect(row.textContent).not.toContain(PLAYERS.jacobs.name);
    }
    expect(screen.getByTestId("picks-out").textContent).toContain(PLAYERS.jacobs.name);
  });

  it("REFUSES a fixture player's figure under a category of the other kind", () => {
    // Robinson's 96 rush yards under "Anytime TD". The fixture's own guard
    // catches this shape too, but only for the mocks; this is the guard a
    // site's adapter would hit, in the component, by name.
    const p = PLAYERS.robinson;
    expect(() =>
      render(
        <PicksList
          categories={[
            {
              category: "Anytime TD",
              rows: [
                {
                  key: "robinson:Anytime TD",
                  name: p.name,
                  detail: "Anytime TD",
                  value: valueOf(p, "Rush yds"),
                  kind: "probability",
                  provenance: "bucket hits n=140",
                },
              ],
            },
          ]}
        />,
      ),
    ).toThrow(RowKindMismatchError);
  });

  it("no fixture row renders a percentage for a projection category", () => {
    render(<PicksList categories={ALL()} />);
    for (const row of screen.getAllByTestId("picks-row").filter((r) => r.getAttribute("data-kind") === "projection")) {
      expect(row.textContent).not.toContain("%");
    }
  });
});