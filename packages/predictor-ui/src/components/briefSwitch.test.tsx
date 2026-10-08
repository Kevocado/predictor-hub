/**
 * The panel's switch to `MatchupBrief` — and, more importantly, what must NOT
 * switch.
 *
 * The rule the switch is built on: **a response with no `slot` renders exactly
 * what it rendered before.** That is the whole compatibility claim, and it is
 * the one thing a screenshot cannot check, because "the old layout" is not a
 * thing a screenshot can be compared against once the code has changed. So it is
 * asserted structurally: the same factors, through the same `FactorList`, with
 * the same rows in the same order and the same direction words, and none of the
 * grouped headings.
 *
 * The two directions that matter:
 *
 *  - **OFF** — a legacy response (no `slot` at all) and a response that has
 *    `matchups` but no slots. The second is the case a `matchups.length` switch
 *    gets wrong: it would print an "Edge" heading over rows the explainer never
 *    slotted, which is a claim about the answer that the answer does not make.
 *  - **ON** — a slotted response, grouped, with the duel drawn for a
 *    `matchup:<id>` row and omitted for one whose duel is absent.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExplainerPanel, type Explanation, type Verdict } from "./ExplainerPanel";
import type { SlottedFactor } from "./MatchupBrief";

const noop = () => {};
const RESTING = { loading: false, error: false, onRetry: noop };

const duel = {
  id: "pass_off_vs_pass_def:home", attacker: "Bills", defender: "Jets",
  stat: "passing offence", foil: "pass defence",
  attacker_rank: 3, defender_rank: 28, n_teams: 32, toward_pick: true,
};

const EDGE_HEADLINE = "Bills' #3 passing offence meets Jets' #28 pass defence";

const slotted: SlottedFactor[] = [
  { key: "matchup:pass_off_vs_pass_def:home", direction: "up", slot: "edge",
    headline: EDGE_HEADLINE, text: "Bills rank 3 of 32 in passing offence; Jets rank 28 of 32 in pass defence." },
  { key: "spread", direction: "neutral", slot: "price",
    headline: "Model -4.0 against a quoted -6.5", text: "Both figures, no verdict on them." },
];

const legacy: Explanation["factors"] = [
  { key: "moneyline", direction: "up", headline: "Model leans Baltimore", text: "The gap has held all week." },
  { key: "record", direction: "neutral", headline: "Its record so far", text: "41 of 68 landed." },
];

function panel(factors: Explanation["factors"] | SlottedFactor[], extra: Record<string, unknown> = {}): Explanation {
  const verdict: Verdict = { verdict: "Bills by about 4. Leaning.", band: "moderate", factors };
  return {
    source: "llm", model: "nemotron-3.5-lightning",
    generated_at: new Date(Date.now() - 60_000).toISOString(),
    sport: "nfl", pick_timing: "pre_kickoff",
    ...verdict, ...extra,
  } as Explanation;
}

describe("ExplainerPanel's switch to MatchupBrief", () => {
  it("a slotted response is grouped, with the duel drawn for a matchup row", () => {
    render(<ExplainerPanel {...RESTING} data={panel(slotted)} matchups={[duel]} />);
    expect(screen.getByRole("heading", { name: "Edge" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Price" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Risk" })).toBeNull();
    expect(within(screen.getByTestId("rank-duel")).getByText("#28", { exact: false })).toBeInTheDocument();
  });

  it("a legacy response renders exactly the old FactorList", () => {
    render(<ExplainerPanel {...RESTING} data={panel(legacy)} />);
    // No grouped headings, ever: an old answer has no slots to group by, and a
    // heading it cannot support is a claim about the answer that is not true.
    expect(screen.queryByRole("heading", { name: "Edge" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Risk" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Price" })).toBeNull();
    // The same rows, the same order, the same direction words `FactorList` drew.
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(legacy.length);
    expect(rows[0]).toHaveTextContent("Model leans Baltimore");
    expect(rows[0]).toHaveTextContent("for the pick");
    expect(rows[1]).toHaveTextContent("context");
    expect(screen.queryByTestId("rank-duel")).toBeNull();
  });

  it("matchups without slots are still the old layout — a switch on matchups would break this", () => {
    render(<ExplainerPanel {...RESTING} data={panel(legacy)} matchups={[duel]} />);
    expect(screen.queryByRole("heading", { name: "Edge" })).toBeNull();
    expect(screen.queryByTestId("rank-duel")).toBeNull();
  });

  it("one slotted row is enough to switch the whole panel", () => {
    // The explainer stamps a slot on EVERY factor, so a partial set is not a state
    // that ships — but "some" is the right test, because it is the only one that
    // cannot silently group rows the service left unslotted into the wrong bucket.
    render(<ExplainerPanel {...RESTING} data={panel([slotted[0], legacy[0]])} matchups={[duel]} />);
    expect(screen.getByRole("heading", { name: "Edge" })).toBeInTheDocument();
    // The unslotted row still renders, as context, rather than disappearing.
    expect(screen.getByTestId("factor-moneyline")).toHaveTextContent("Model leans Baltimore");
  });

  it("a matchup factor with no duel renders its words and no bars", () => {
    render(<ExplainerPanel {...RESTING} data={panel(slotted)} matchups={[]} />);
    expect(screen.queryByTestId("rank-duel")).toBeNull();
    expect(screen.getByText(/#3 passing offence/)).toBeInTheDocument();
  });

  it("a duel whose ranks the headline does not state is refused, not drawn", () => {
    expect(() => render(
      <ExplainerPanel {...RESTING}
        data={panel([{ ...slotted[0], headline: "Their passing game against that pass defence" }])}
        matchups={[duel]} />,
    )).toThrow(/headline/i);
  });

  it("selecting a row in the brief still lights the figure the panel draws for it", async () => {
    const tiles = [{ market: "spread", label: "Spread", value: "BAL -2.5", sub: "model -3.4" }];
    render(<ExplainerPanel {...RESTING} data={panel(slotted)} matchups={[duel]} tiles={tiles} />);
    const row = screen.getByTestId("factor-spread");
    expect(row).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(row);
    expect(row).toHaveAttribute("aria-pressed", "true");
  });

  it("a duel row has no figure to light, so pressing it clears rather than lights", async () => {
    const tiles = [{ market: "spread", label: "Spread", value: "BAL -2.5", sub: "model -3.4" }];
    render(<ExplainerPanel {...RESTING} data={panel(slotted)} matchups={[duel]} tiles={tiles} />);
    const duelRow = screen.getByTestId("factor-matchup:pass_off_vs_pass_def:home");
    await userEvent.click(duelRow);
    // The panel's own guard: a key with no figure under it clears the highlight, so
    // every row means "light the figure, or clear the light". It stays a control.
    expect(duelRow).toHaveAttribute("aria-pressed", "false");
  });

  it("the slot travels in the response type, so a site passes it without a cast", () => {
    // Compile-time, and the reason `Factor` keeps `slot` optional: a site building
    // a panel prop typed as `Explanation` must not have to widen it.
    const v: Verdict = { verdict: "v", band: "leaning", factors: [{ ...slotted[0] }] };
    expect(v.factors[0].slot).toBe("edge");
  });
});

describe("ExplainerPanel keeps everything else it had", () => {
  it("the verdict, band and footer are unchanged by the switch", () => {
    render(<ExplainerPanel {...RESTING} data={panel(slotted)} matchups={[duel]} />);
    expect(screen.getByText("Bills by about 4. Leaning.")).toBeInTheDocument();
    expect(screen.getByText("Moderate")).toBeInTheDocument();
    expect(screen.getByText(/nemotron-3.5-lightning/)).toBeInTheDocument();
  });

  it("a rebuilt pick still discloses itself, grouped or not", () => {
    render(<ExplainerPanel {...RESTING} data={panel(slotted, { pick_timing: "rebuilt" })} matchups={[duel]} />);
    expect(screen.getByText(/Counted in the track record like any other pick/)).toBeInTheDocument();
    expect(screen.getByText(/Made after kickoff/)).toBeInTheDocument();
    // No band on a rebuilt pick, exactly as before: the switch does not touch it.
    expect(screen.queryByText("Moderate")).toBeNull();
  });

  it("an unknown `slot` value from the wire is not drawn as a heading", () => {
    // A renamed value on the wire must fall back to the old list rather than
    // inventing a group. `groupBySlot` reads it as `context` because it is not one
    // of the four it knows, which is the same fail-closed move the direction
    // default makes.
    render(
      <ExplainerPanel {...RESTING}
        data={panel([{ ...slotted[0], slot: "tilt" as unknown as "edge" }])} matchups={[duel]} />,
    );
    expect(screen.queryByRole("heading", { name: "tilt" })).toBeNull();
    expect(screen.getByTestId("factor-matchup:pass_off_vs_pass_def:home")).toBeInTheDocument();
  });

  it("a site that passes no matchups at all gets the grouped layout without duels", () => {
    render(<ExplainerPanel {...RESTING} data={panel(slotted)} />);
    expect(screen.getByRole("heading", { name: "Edge" })).toBeInTheDocument();
    expect(screen.queryByTestId("rank-duel")).toBeNull();
  });

  it("the onSelect guard is not bypassed by the brief", async () => {
    const onSelect = vi.fn();
    render(<ExplainerPanel {...RESTING} data={panel(slotted)} matchups={[duel]} onRetry={onSelect} />);
    await userEvent.click(screen.getByTestId("factor-spread"));
    expect(onSelect).not.toHaveBeenCalled();   // pressing a row is not retrying
  });
});