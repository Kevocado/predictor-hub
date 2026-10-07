/** The v2 panel's parts, tested as structure rather than appearance.
 *
 *  What these can prove: shape, keyboard operability, the numbers in accessible
 *  names, and the rules that make a figure safe (no derived percentage, nothing
 *  for an absent market, a band the caller may not invent). What they cannot
 *  prove is whether a proportion *reads* right — that needs a browser, and the
 *  screenshots in the PR are the evidence for it.
 *
 *  One deviation from the plan, forced by the code rather than chosen: the plan
 *  added a new `ProbabilitySplit`. `ProbabilityBar` already exists and already
 *  owns "a probability breakdown, labelled in words", so a second bar in one
 *  package would be a design system forking itself. `ProbabilityBar` is extended
 *  instead, and its existing callers are unaffected because every addition is
 *  optional.
 */
import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import * as ts from "typescript";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ExplainerPanel, FactorList, KeyNumberTile, RecordStrip } from "../index";
import { ProbabilityBar } from "./ProbabilityBar";
import type { Common, Explanation, MarketTile, Segment, Verdict } from "../index";

/** The §7a NFL mock's facts, so the fixtures and the spec cannot drift. */
const NFL: Explanation = {
  verdict: "Baltimore is the pick, but the line is thinner than the number.",
  band: "moderate",
  factors: [
    { key: "moneyline", direction: "up", headline: "Model leans Baltimore",
      text: "The rating gap has held all week and the model has not moved off it." },
    { key: "spread", direction: "down", headline: "The line asks more than the margin",
      text: "The market is asking for more than the model thinks the gap is worth." },
  ],
  source: "llm", model: "nemotron-3.5-lightning", generated_at: new Date().toISOString(),
  sport: "nfl", pick_timing: "pre_kickoff",
};

const TILES: MarketTile[] = [
  { market: "moneyline", label: "62%", value: "62%", sub: "win · BAL" },
  { market: "spread", label: "BAL −2.5", value: "BAL −2.5", sub: "model −3.4" },
  { market: "total", label: "45.2", value: "45.2", sub: "total pts · line 44.5" },
];

/** The panel's required props, so a test can render the resting state in one
 *  call. `loading`/`error`/`onRetry` are required by the component because every
 *  real caller has them; passing them per test buried the thing under test. */
const RESTING = { loading: false, error: false, onRetry: () => {} };

/** A complete v2 answer, overridable, so a test names only what it is about. */
const answer = (over: Partial<Explanation> = {}): Explanation => ({ ...NFL, ...over });

/** The no-pick bundle `template.py` actually emits, taken from the rows that
 *  need no pick to be written: `record` (`template.py:164`), the `context`
 *  padding (`:178`/`:184`), and the two pseudo-market statements `total` and
 *  `btts`, which are written whether or not a pick exists (`:139`, `:146`).
 *  `record` and `context` are the two that can never resolve: they are the
 *  record strip and the game's context, not markets, so no site hands the panel
 *  a tile or a bar segment under either key. `total` is carried here so a test
 *  cannot pass by there being nothing linkable on the panel at all. */
const NO_PICK: Common & Verdict = {
  verdict: "There is no pick for this one yet.",
  band: "leaning",
  factors: [
    { key: "total", direction: "neutral", headline: "The total", text: "It projects 45.2 points against a line of 44.5." },
    { key: "record", direction: "neutral", headline: "Its record so far", text: "41 of 68 picks have landed." },
    { key: "context", direction: "neutral", headline: "Where this stands", text: "So there is little to weigh up here." },
  ],
  source: "template", model: "", generated_at: new Date().toISOString(),
  sport: "nfl", pick_timing: "none",
};

const SEGMENTS: Segment[] = [
  { label: "KC", prob: 0.38, market: "moneyline" },
  { label: "BAL", prob: 0.62, market: "spread" },
];

/** The §7a bar as the facts carry it: the away side is listed first for US
 *  sports, so the pick is the SECOND segment. This is the shape from the
 *  screenshot, and the reason emphasis has to be found by label — a rule that
 *  reads position picks KC here, which is the wrong side on every count. */
const NFL_BAR: Segment[] = [
  { label: "KC", prob: 0.38, market: "moneyline" },
  { label: "BAL", prob: 0.62, market: "moneyline" },
];

/** PL's three-way result market, home / draw / away. */
const PL_BAR: Segment[] = [
  { label: "Arsenal", prob: 0.48, market: "result" },
  { label: "Draw", prob: 0.26, market: "result" },
  { label: "Chelsea", prob: 0.26, market: "result" },
];

const ACCENT = "var(--color-pr-accent)";
const NEUTRALS = ["var(--color-pr-text-dim)", "var(--color-pr-text-faint)", "var(--color-pr-fill-mute)"];

/** The market's own split, which is a DIFFERENT set of numbers from the model's.
 *  Deliberately not a copy of `PL_BAR` with a new label: every figure differs, so
 *  a test that reads the wrong array cannot pass by coincidence. */
const MARKET: Segment[] = [
  { label: "Arsenal", prob: 0.44 },
  { label: "Draw", prob: 0.25 },
  { label: "Chelsea", prob: 0.31 },
];

/** What each segment is actually painted, in order. */
function fills(container: HTMLElement): string[] {
  return [...container.querySelectorAll<HTMLElement>("[data-testid='pbar-fill']")].map((f) => f.style.backgroundColor);
}

/** How far each segment is dimmed, in order. The §13c de-emphasis is applied as
 *  an opacity rather than a colour so a dimmed figure stays the figure it was,
 *  so this reads the thing the reader sees. */
function dims(container: HTMLElement): string[] {
  return [...container.querySelectorAll<HTMLElement>("[data-testid='pbar-fill']")].map((f) => f.style.opacity);
}

describe("KeyNumberTile", () => {
  it("shows the model's figure large with its own label beneath", () => {
    render(<KeyNumberTile tile={TILES[0]} />);
    expect(screen.getByText("62%")).toBeInTheDocument();
    expect(screen.getByText("win · BAL")).toBeInTheDocument();
  });

  it("renders nothing at all for an absent market, never a dash or a zero", () => {
    // Spec §6: an absent market renders nothing. A dash would read as "we looked
    // and there is nothing", and a 0% would be a figure no fact carries.
    const { container } = render(<KeyNumberTile tile={{ market: "total", label: "", value: "" }} />);
    expect(container.firstChild).toBeNull();
  });

  it("marks itself when a factor references its market", () => {
    render(<KeyNumberTile tile={TILES[1]} highlighted />);
    expect(screen.getByTestId("tile-spread")).toHaveAttribute("data-highlighted", "true");
  });

  it("is a definition list, so the label/value pairing is structural", () => {
    render(<KeyNumberTile tile={TILES[0]} />);
    expect(screen.getByTestId("tile-moneyline").tagName).toBe("DL");
  });

  it("prints the market's LABEL where a label goes, never the key the facts join on", () => {
    // Kevin's tile. `market` is the identifier — "btts", "total_goals",
    // "moneyline" — and the tile used to fall back to it, so a caller who passed a
    // label and no market line got the key in the one slot on the tile reserved
    // for words. It failed silently, because `label` was required, was type
    // checked, and was never rendered anywhere in the component.
    render(<KeyNumberTile tile={{ market: "btts", label: "Both teams score", value: "61%" }} />);
    expect(screen.getByText("Both teams score")).toBeInTheDocument();
    expect(screen.queryByText("btts")).toBeNull();
    expect(document.body.textContent).not.toMatch(/btts/);
  });

  it("still lets a market line stand in for the label", () => {
    render(<KeyNumberTile tile={{ market: "total_goals", label: "Total goals", value: "2.7", sub: "Over 2.5 · 56%" }} />);
    expect(screen.getByText("Over 2.5 · 56%")).toBeInTheDocument();
    // A `dl` has no name of its own, so its accessible name IS its content: a key
    // in the text is a key in the name, and there is no second surface to fix.
    const tile = screen.getByTestId("tile-total_goals");
    expect(tile.textContent).not.toMatch(/total_goals/);
    expect(tile.textContent).not.toMatch(/[OU]\d/);
  });
});

describe("ProbabilityBar", () => {
  it("carries the same figures in words for a screen reader", () => {
    render(<ProbabilityBar segments={SEGMENTS} />);
    expect(screen.getByRole("img", { name: "KC 38%, BAL 62%" })).toBeInTheDocument();
  });

  it("still serves its existing callers, which pass no legend", () => {
    // The pre-panel call sites pass {label, prob} and nothing else. If adding the
    // panel's options broke them, this is what would notice.
    render(<ProbabilityBar segments={[{ label: "A", prob: 0.6 }, { label: "B", prob: 0.4 }]} />);
    expect(screen.getByRole("img", { name: "A 60%, B 40%" })).toBeInTheDocument();
  });

  it("omits the market row entirely unless it covers every outcome", () => {
    // §13b. PL's `implied` carries only the two sides, so a three-way split with
    // a two-way market row would put the draw segment above nothing.
    const three = [
      { label: "Arsenal", prob: 0.48, market: "result" },
      { label: "Draw", prob: 0.26, market: "result" },
      { label: "Chelsea", prob: 0.26, market: "result" },
    ];
    const { rerender } = render(<ProbabilityBar segments={three} legend={[{ label: "Arsenal", prob: 0.44 }, { label: "Chelsea", prob: 0.3 }]} />);
    expect(screen.queryByTestId("pbar-legend")).toBeNull();

    rerender(<ProbabilityBar segments={three} legend={[
      { label: "Arsenal", prob: 0.44 }, { label: "Draw", prob: 0.25 }, { label: "Chelsea", prob: 0.31 },
    ]} />);
    expect(screen.getByTestId("pbar-legend")).toBeInTheDocument();
  });

  it("shows a 3% segment its label on focus, and keeps it a sliver", () => {
    // The reader this is for is stepping through the figures to find the sliver's
    // own, so this is the branch where the labels are controls — which is the
    // branch that exists whenever a caller is listening for a focus. The
    // handler is a no-op here because the thing under test is the rendered
    // affordance; `ExplainerPanel` supplies a real one.
    render(<ProbabilityBar segments={[{ label: "A", prob: 0.97 }, { label: "B", prob: 0.03 }]} minSegmentPx={2} onSegmentFocus={() => {}} />);
    const seg = document.querySelector<HTMLButtonElement>('[data-seg="B"]')!;
    expect(seg).toHaveTextContent("3%");
    seg.focus();
    expect(seg).toHaveFocus();
    // The sliver is the FILL's job: the label is text and never shrinks.
    expect(document.querySelector('[data-testid="pbar-fill"][data-min-width]')).toBeTruthy();
  });

  it("makes the segment labels operable only for a caller that can be told about it", () => {
    // The bar's segment buttons exist to report a focus to someone (§13c), and
    // they are buttons for exactly that reason and no other. With no
    // `onSegmentFocus` they would be announced as controls, reachable by
    // keyboard, and inert — a focus stop that lies — and on a surface already
    // wrapped in a button (a match card) that is also invalid HTML. So with
    // nobody listening they are text.
    const { rerender, container } = render(<ProbabilityBar segments={SEGMENTS} />);
    const figures = () => [...container.querySelectorAll("[data-seg]")].map((n) => n.textContent);
    expect(figures()).toEqual(["KC 38%", "BAL 62%"]);
    for (const label of container.querySelectorAll("[data-seg]")) expect(label.tagName).not.toBe("BUTTON");

    rerender(<ProbabilityBar segments={SEGMENTS} onSegmentFocus={() => {}} />);
    for (const label of container.querySelectorAll("[data-seg]")) expect(label.tagName).toBe("BUTTON");
    // Same figures either way, and still in the bar's name, so a reader who
    // cannot step through them has every one of them.
    expect(figures()).toEqual(["KC 38%", "BAL 62%"]);
    expect(screen.getByRole("img", { name: "KC 38%, BAL 62%" })).toBeInTheDocument();
  });

  it("is operable by keyboard alone, which is what catches a div with onClick", async () => {
    const user = userEvent.setup();
    const onSegmentFocus = vi.fn();
    render(<ProbabilityBar segments={SEGMENTS} onSegmentFocus={onSegmentFocus} />);
    const seg = document.querySelector<HTMLButtonElement>('[data-seg="BAL"]')!;
    expect(seg.tagName).toBe("BUTTON");
    seg.focus();
    await user.keyboard("{Enter}");
    expect(onSegmentFocus).toHaveBeenCalledWith("BAL", "spread");
  });
});

/** The defect from the screenshot: the accent is a claim about the PICK, and
 *  segment order is not the pick. On the §7a bar the away side is listed first,
 *  so an index-driven fill painted KC 38% and greyed BAL 62% — the model shown
 *  having picked the side it picked least of. */
describe("the pick is the accented segment", () => {
  it("accents the pick's segment, and the pick here is the second one", () => {
    const { container } = render(<ProbabilityBar segments={NFL_BAR} pick={{ label: "BAL" }} />);
    expect(fills(container)).toEqual([NEUTRALS[0], ACCENT]);
  });

  it("accents the pick wherever it sits on a three-way bar, and keeps three tones", () => {
    // The pick is given the accent; the two segments that are not the pick walk
    // the neutral ramp, so the draw never lands on the same grey as a side —
    // which would make a 48% home and a 26% draw indistinguishable by tone.
    for (const [i, label] of ["Arsenal", "Draw", "Chelsea"].entries()) {
      const { container, unmount } = render(<ProbabilityBar segments={PL_BAR} pick={{ label }} />);
      const tones = fills(container);
      expect(tones[i], label).toBe(ACCENT);
      expect(tones.filter((_, j) => j !== i), label).toHaveLength(2);
      expect(new Set(tones).size, label).toBe(3);
      expect(tones.filter((t) => t !== ACCENT).every((t) => NEUTRALS.includes(t)), label).toBe(true);
      unmount();
    }
  });

  it("accents nothing at all when there is no pick", () => {
    // A bar that emphasises something is claiming there is a pick. With none,
    // "the first one is" is the same defect one segment over, and it is the
    // case that pairs with a no-pick answer saying "for the pick".
    const { container } = render(<ProbabilityBar segments={NFL_BAR} />);
    expect(fills(container)).not.toContain(ACCENT);
    expect(fills(container)).toEqual([NEUTRALS[0], NEUTRALS[1]]);
  });

  it("keeps a three-way bar's three tones with no pick, and spends no accent on one", () => {
    const { container } = render(<ProbabilityBar segments={PL_BAR} />);
    const tones = fills(container);
    expect(new Set(tones).size).toBe(3);
    expect(tones).not.toContain(ACCENT);
  });

  it("still lets a legible team colour win, even on the pick's own segment", () => {
    // The 1.6:1 floor is a legibility rule, not a pick rule: a team's colour is
    // a fact about the team, and overpainting it to mean "the pick" would put a
    // second claim on top of the first. So the colour wins and the emphasis is
    // carried in the name instead (asserted below).
    const { container } = render(
      <ProbabilityBar
        segments={[{ label: "PIT", prob: 0.45, color: "#FFB612" }, { label: "CLE", prob: 0.55, color: "#311D00" }]}
        pick={{ label: "CLE" }}
      />,
    );
    expect(fills(container)).toEqual(["rgb(255, 182, 18)", ACCENT]);
  });

  it("keeps both team colours when both are legible, and says the pick in the name", () => {
    // The honest limit of the colour rule, pinned rather than hidden: with two
    // readable team colours there is no accent left to spend, so the name is
    // what carries the pick. Two bright team colours are not an emphasis we can
    // add without overpainting one of them.
    render(
      <ProbabilityBar
        segments={[{ label: "KC", prob: 0.38, color: "#E31837" }, { label: "BAL", prob: 0.62, color: "#4C8DFF" }]}
        pick={{ label: "BAL" }}
      />,
    );
    expect(screen.getByRole("img")).toHaveAccessibleName("KC 38%, BAL 62%, the pick is BAL");
  });

  it("drops an illegible team colour for the ramp, so the pick still shows", () => {
    // Ravens purple is 1.3:1 on the panel and disappears; the pick on that
    // segment has to come from the accent or the emphasis is invisible.
    const { container } = render(
      <ProbabilityBar
        segments={[{ label: "KC", prob: 0.38, color: "#E31837" }, { label: "BAL", prob: 0.62, color: "#241773" }]}
        pick={{ label: "BAL" }}
      />,
    );
    expect(fills(container)).toEqual(["rgb(227, 24, 55)", ACCENT]);
  });

  it("accents nothing when the pick's label matches no segment here", () => {
    // Fails closed. A site passing a different vocabulary must not have the
    // panel point at the segment nearest to the pick.
    const { container } = render(<ProbabilityBar segments={NFL_BAR} pick={{ label: "Baltimore Ravens" }} />);
    expect(fills(container)).not.toContain(ACCENT);
    expect(screen.getByRole("img")).toHaveAccessibleName("KC 38%, BAL 62%");
  });

  it("names the pick for a reader who cannot see which segment is accented", () => {
    // The same rule FactorList states about its triangles: a meaning carried by
    // colour alone is not carried at all.
    const { unmount } = render(<ProbabilityBar segments={NFL_BAR} pick={{ label: "BAL" }} />);
    expect(screen.getByRole("img")).toHaveAccessibleName("KC 38%, BAL 62%, the pick is BAL");
    unmount();
    // And with no pick the name is unchanged, so the pre-panel call sites are not
    // given a clause they never asked for.
    render(<ProbabilityBar segments={NFL_BAR} />);
    expect(screen.getByRole("img")).toHaveAccessibleName("KC 38%, BAL 62%");
  });
});

/** The market row, from the screenshot: the word `market`, a row of grey bars,
 *  and no figures at all. The bar is the whole point of the row — it is the
 *  comparison between the model's split and the market's — and it cannot be read
 *  without them, because a bar is only comparable to another bar once you know
 *  what each end of it is. */
describe("the market row is labelled with the market's own figures", () => {
  it("states the market's percentages under the model's, in the same columns", () => {
    const { container } = render(<ProbabilityBar segments={PL_BAR} legend={MARKET} pick={{ label: "Arsenal" }} />);
    const figures = within(within(container).getByTestId("pbar-market-figures"));
    expect(figures.getByText("Arsenal 44%")).toBeInTheDocument();
    expect(figures.getByText("Draw 25%")).toBeInTheDocument();
    expect(figures.getByText("Chelsea 31%")).toBeInTheDocument();
    // The whole point: each market figure is in the column of the model figure it
    // is being compared with, so the reader compares down and not across.
    expect([...container.querySelectorAll("[data-market]")].map((el) => el.textContent)).toEqual(
      ["Arsenal 44%", "Draw 25%", "Chelsea 31%"],
    );
  });

  it("quotes the MARKET's numbers, not the model's — the attribution trap", () => {
    // Two bars, two splits, one prop each, and reading the wrong array produces
    // a comparison made entirely of real numbers attributed to the wrong source.
    // That is worse than no row: there is nothing on screen a reader could use to
    // notice. Asserted in the visible text AND in the accessible name, because
    // the name is the whole of what a reader who cannot see the bars is given.
    const { container } = render(<ProbabilityBar segments={PL_BAR} legend={MARKET} />);
    const row = within(container).getByTestId("pbar-market-figures");
    expect(row.textContent).not.toMatch(/48%|26%/);
    expect(screen.getByRole("img", { name: "market: Arsenal 44%, Draw 25%, Chelsea 31%" })).toBeInTheDocument();
    // And the bar's own widths, which is the other half of the same claim.
    const growth = [...container.querySelectorAll<HTMLElement>("[data-testid='pbar-market-fill']")].map(
      (el) => el.style.flexGrow,
    );
    expect(growth).toEqual(["0.44", "0.25", "0.31"]);
  });

  it("reads the market's figures by label, so a differently ordered legend still lines up", () => {
    // `segments` and `legend` are two different facts. Pairing them by index would
    // print the market's 44% under the model's 48% and still look like a comparison.
    const shuffled = [MARKET[2], MARKET[0], MARKET[1]];
    const { container } = render(<ProbabilityBar segments={PL_BAR} legend={shuffled} />);
    expect([...container.querySelectorAll("[data-market]")].map((el) => el.textContent)).toEqual([
      "Arsenal 44%",
      "Draw 25%",
      "Chelsea 31%",
    ]);
  });

  it("omits the row when the market covers an outcome the model's split does not", () => {
    // The other direction of §13b, and the one that matters for the labels: a
    // market segment with no model column above it cannot be compared with
    // anything, and the figures below the two bars would stop lining up too.
    render(<ProbabilityBar segments={PL_BAR} legend={[...MARKET, { label: "Brighton", prob: 0.07 }]} />);
    expect(screen.queryByTestId("pbar-legend")).toBeNull();
  });

  it("sets every figure in the bar and the market row at the 12px floor or above", () => {
    // §6a's floor, asserted on the class the component actually emits. A size a
    // reader sees is a size in the markup, and the failure the floor exists to
    // prevent is exactly "set this one smaller so the row fits" — so the check is
    // over both rows, not just the one a screenshot happened to show.
    const { container } = render(
      <ProbabilityBar segments={PL_BAR} legend={MARKET} minSegmentPx={2} pick={{ label: "Arsenal" }} />,
    );
    const sized = [...container.querySelectorAll<HTMLElement>("*")].filter((el) =>
      [...el.childNodes].some((n) => n.nodeType === 3 && (n.textContent ?? "").trim() !== ""),
    );
    // Both rows really are in there, or this test is checking nothing.
    expect(sized.length).toBeGreaterThanOrEqual(PL_BAR.length * 2);
    for (const el of sized) {
      const classes = el.className;
      expect(classes, el.textContent ?? "").toMatch(/\btext-(xs|sm|base|lg|xl|2xl|3xl)\b/);
      for (const [, px] of classes.matchAll(/text-\[(\d+(?:\.\d+)?)px\]/g)) {
        expect(Number(px), `${px}px is under the floor`).toBeGreaterThanOrEqual(12);
      }
    }
  });

  it("falls back to the bare bar behind a real aria-expanded button on a narrow surface", async () => {
    // The same shape FactorList uses for a clamped sentence: opt in, get a real
    // button, and collapse to a narrower form. Off by default, so a wide layout
    // never hides figures behind a control that adds nothing — and OPEN when it
    // is on, because an unlabelled market bar is the defect these figures fix.
    const user = userEvent.setup();
    const { container, rerender } = render(<ProbabilityBar segments={PL_BAR} legend={MARKET} />);
    expect(screen.queryByTestId("pbar-market-toggle")).toBeNull();
    expect(within(container).getByTestId("pbar-market-figures")).toBeInTheDocument();

    rerender(<ProbabilityBar segments={PL_BAR} legend={MARKET} expandable />);
    const toggle = screen.getByTestId("pbar-market-toggle");
    expect(toggle.tagName).toBe("BUTTON");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(within(container).getByTestId("pbar-market-figures")).toBeInTheDocument();

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("pbar-market-figures")).toBeNull();
    // Collapsed, not gone: the comparison bar and the word that names it remain,
    // which is the only thing the fallback is allowed to drop.
    expect(within(container).getByTestId("pbar-legend")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "market: Arsenal 44%, Draw 25%, Chelsea 31%" })).toBeInTheDocument();

    await user.click(toggle);
    expect(within(container).getByTestId("pbar-market-figures")).toBeInTheDocument();
  });
});

describe("FactorList", () => {
  it("never carries the direction by colour alone", () => {
    render(<FactorList factors={NFL.factors} />);
    // The words are the point; the glyph is decoration beside them.
    expect(screen.getByText(/for the pick/i)).toBeInTheDocument();
    expect(screen.getByText(/against it/i)).toBeInTheDocument();
  });

  it("draws its direction marks rather than borrowing unicode triangles", () => {
    const { container } = render(<FactorList factors={NFL.factors} />);
    expect(container.querySelectorAll("svg[data-direction]")).toHaveLength(2);
    // The craft floor refuses unicode glyphs standing in for an icon system, and
    // the §7a mock's ▲/▼ are exactly that.
    expect(container.textContent).not.toMatch(/[▲▼]/);
  });

  it("makes every row a real button, so it is keyboard reachable", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<FactorList factors={NFL.factors} onSelect={onSelect} />);
    const row = screen.getByRole("button", { name: /model leans baltimore/i });
    expect(row.tagName).toBe("BUTTON");
    row.focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith("moneyline");
  });

  it("expands a clamped sentence behind a real aria-expanded button", async () => {
    const user = userEvent.setup();
    const { container } = render(<FactorList factors={NFL.factors} expandable />);
    // One "More" per factor, so pick the row rather than a name that repeats.
    const toggle = within(container.querySelectorAll("li")[1]).getByRole("button", { name: /more/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(container.querySelector("[data-expanded='true']")).toBeTruthy();
  });
});

/** A factor with no direction: a statement about the game, the record, or how
 *  little there is to weigh up — and, with no pick, every factor in the panel.
 *  The words are the accessible truth (rule 1), so a row that draws a triangle
 *  and a colour is making a claim in colour, and a row whose colour came from
 *  `direction !== "up"` made the opposite one: "against it". */
describe("a factor with no direction", () => {
  const NEUTRAL_FACTORS = [
    { key: "total", direction: "neutral" as const, headline: "It projects 45.2 points", text: "The line is 44.5." },
    { key: "record", direction: "neutral" as const, headline: "Its record so far", text: "41 of 68 have landed." },
  ];

  it("draws no mark at all, and wears neither the win nor the loss colour", () => {
    const { container } = render(<FactorList factors={NEUTRAL_FACTORS} />);
    // No triangle in either direction: the mark is the direction, and there is
    // none. One per up/down row is what the test above pins, so this is the
    // negative of it.
    expect(container.querySelectorAll("svg[data-direction]")).toHaveLength(0);
    expect(container.querySelector(".text-pr-win")).toBeNull();
    expect(container.querySelector(".text-pr-loss")).toBeNull();
  });

  it("says what the row is, not which way it leans", () => {
    render(<FactorList factors={NEUTRAL_FACTORS} />);
    expect(screen.getAllByText(/context/i)).toHaveLength(2);
    // The words Kevin's screenshot was really about. There is no pick to be for
    // or against, so neither phrase may appear anywhere in a neutral row.
    expect(document.body.textContent).not.toMatch(/for the pick|against it/i);
  });

  it("keeps the up and down words, and their marks, exactly as they were", () => {
    // The other half, so neutral cannot become a way of losing the panel's
    // argument: a factor that is really for or against still says so.
    const { container } = render(<FactorList factors={NFL.factors} />);
    expect(screen.getByText(/for the pick/i)).toBeInTheDocument();
    expect(screen.getByText(/against it/i)).toBeInTheDocument();
    expect(container.querySelectorAll("svg[data-direction]")).toHaveLength(2);
  });

  it("is still a real button, and still expands, like any other row", async () => {
    // What is withheld here is the claim, not the function: a reader who wants
    // the full sentence gets it, and keyboard-only reachability is unchanged.
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const { container } = render(<FactorList factors={NEUTRAL_FACTORS} onSelect={onSelect} expandable />);
    const toggle = within(container.querySelectorAll("li")[0]).getByRole("button", { name: /more/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const row = screen.getByRole("button", { name: /it projects 45\.2 points/i });
    expect(row.tagName).toBe("BUTTON");
    row.focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith("total");
  });
});

describe("RecordStrip", () => {
  it("states n / n and never a percentage the facts do not contain", () => {
    // §5a-bis. `record` is hits/settled; the facts hold no 60.3, so the bar's
    // width is the proportion and the text is the two numbers.
    render(<RecordStrip label="Picks made before kickoff" hits={41} settled={68} />);
    expect(screen.getByText("41/68")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /41 of 68/ })).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/60\.3|60%|82%/);
  });

  it("shows a dash when nothing is settled, never 0/0", () => {
    render(<RecordStrip label="r" hits={0} settled={0} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows a dash for a record it cannot read, and never quotes half of one", () => {
    // `hits` and `settled` are two fields of ONE `record` object in the facts, so
    // `hits: null, settled: 68` is an object this component cannot read rather
    // than a record missing its numerator. "—/68" would show the 68 — and would
    // be quoting the denominator of an object whose numerator we have just
    // declined to trust, which is the same mistake as drawing the bar 0% wide.
    // The ruling and the trade-off it costs are written at the branch in
    // `RecordStrip.tsx`; this is the test that makes it a decision.
    const { container } = render(<RecordStrip label="Picks made before kickoff" hits={null} settled={68} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText(/68/)).toBeNull();
    expect(container.querySelector("[data-testid='record-fill']")).toBeNull();
  });

  it("shows rebuilt count when provided", () => {
    render(<RecordStrip label="Every pick" hits={1174} settled={1373} rebuilt={1365} />);
    expect(screen.getByText("1174/1373")).toBeInTheDocument();
    expect(screen.getByText("1365 of them made after tip-off")).toBeInTheDocument();
  });

  it("shows pre-tip subset when provided", () => {
    render(<RecordStrip label="Every pick" hits={1174} settled={1373} rebuilt={1365} preTip={{ hits: 3, settled: 8 }} />);
    expect(screen.getByText("1174/1373")).toBeInTheDocument();
    expect(screen.getByText("1365 of them made after tip-off")).toBeInTheDocument();
    expect(screen.getByText("Before tip-off: 3 of 8")).toBeInTheDocument();
  });

  it("shows pre-tip without rebuilt when rebuilt is zero", () => {
    render(<RecordStrip label="Every pick" hits={10} settled={20} rebuilt={0} preTip={{ hits: 5, settled: 10 }} />);
    expect(screen.getByText("10/20")).toBeInTheDocument();
    expect(screen.queryByText(/made after tip-off/)).toBeNull();
    expect(screen.queryByText("0 of them made after tip-off")).toBeNull();
    expect(screen.getByText("Before tip-off: 5 of 10")).toBeInTheDocument();
  });
});

describe("ExplainerPanel", () => {
  it("renders the verdict, the band, the tiles, the split and the factors", () => {
    render(<ExplainerPanel {...RESTING} data={NFL} tiles={TILES} segments={SEGMENTS} />);
    expect(screen.getByRole("heading", { name: /in plain english/i })).toBeInTheDocument();
    expect(screen.getByText(NFL.verdict)).toBeInTheDocument();
    expect(screen.getByText("Moderate")).toBeInTheDocument();
    expect(screen.getByTestId("tile-moneyline")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /KC 38%/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /why it matters/i })).toBeInTheDocument();
  });

  it("links a factor to the figure it names, and clears on Escape", async () => {
    // §13c's first affordance, one direction: a *why* row names the market key
    // it is about, and the tile and the bar segment carrying that key light up.
    // `SEGMENTS` is crossed on purpose — `BAL` is the `spread` segment and `KC`
    // is the `moneyline` one — so pairing a figure to a factor by POSITION or by
    // LABEL lights the wrong element and fails here. The negatives are the half
    // that was missing: without them a panel that highlighted every figure and
    // every tile would satisfy every assertion above.
    const user = userEvent.setup();
    render(<ExplainerPanel {...RESTING} data={NFL} tiles={TILES} segments={SEGMENTS} />);
    await user.click(screen.getByRole("button", { name: /the line asks more/i }));
    expect(screen.getByTestId("tile-spread")).toHaveAttribute("data-highlighted", "true");
    expect(document.querySelector('[data-seg="BAL"]')).toHaveAttribute("data-highlighted", "true");
    expect(screen.getByTestId("tile-moneyline")).toHaveAttribute("data-highlighted", "false");
    expect(document.querySelector('[data-seg="KC"]')).toHaveAttribute("data-highlighted", "false");
    await user.keyboard("{Escape}");
    expect(screen.getByTestId("tile-spread")).toHaveAttribute("data-highlighted", "false");
    expect(document.querySelector('[data-seg="BAL"]')).toHaveAttribute("data-highlighted", "false");
  });

  it("links a figure to the market it names, the other way round, and clears on Escape", async () => {
    // The direction the segment labels exist for. It was unguarded: this panel's
    // only highlight test started at a factor, so it never once drove the
    // figures, and it stayed green when `SegmentFigure` stopped rendering them as
    // controls at all (task D's mutation 2) — the handler was never exercised
    // from this end, and a label that is not a control cannot be reached or
    // activated. `ProbabilityBar`'s own tests pass `onSegmentFocus` themselves,
    // so they cannot see whether `ExplainerPanel` passes it; only rendering
    // through the panel can.
    //
    // Driven through `userEvent`, not a raw `.focus()`, and not `fireEvent`:
    // the event is wrapped in `act`, so the state update the handler makes is
    // flushed the way a reader's would be, instead of React warning that the
    // panel updated outside one. It also gives the mutation above a second,
    // independent catch — `userEvent` focuses what it clicks, and it will not
    // focus a `<span>`, so a figure that stopped being a control loses the focus
    // as well as the highlight. Asserting the RESULT, not the tag name, is the
    // point: the claim is that activating a figure does something.
    const user = userEvent.setup();
    render(<ExplainerPanel {...RESTING} data={NFL} tiles={TILES} segments={SEGMENTS} />);
    const figure = document.querySelector<HTMLElement>('[data-seg="BAL"]')!;
    await user.click(figure);
    expect(figure).toHaveFocus();
    // What the figure NAMES, which is its own `market` key and not its label:
    // `BAL` is the `spread` segment and `spread` is the `KC`-less tile, so
    // looking the tile up by the figure's label, or by position, is caught.
    expect(screen.getByTestId("tile-spread")).toHaveAttribute("data-highlighted", "true");
    expect(screen.getByTestId("tile-moneyline")).toHaveAttribute("data-highlighted", "false");
    // And the figure lights itself, the segment it is: same key, both places.
    expect(document.querySelector('[data-seg="BAL"]')).toHaveAttribute("data-highlighted", "true");
    expect(document.querySelector('[data-seg="KC"]')).toHaveAttribute("data-highlighted", "false");
    await user.keyboard("{Escape}");
    expect(screen.getByTestId("tile-spread")).toHaveAttribute("data-highlighted", "false");
    expect(document.querySelector('[data-seg="BAL"]')).toHaveAttribute("data-highlighted", "false");
  });

  // §13c reads "Both directions highlight", and the third one — a figure
  // lighting the *factor* that names it — was recorded as a todo, because
  // `FactorList` had no prop that could receive the highlight and
  // `expect(row).toHaveAttribute("data-highlighted", "false")` would have pinned
  // the gap shut and failed the day somebody implemented it.
  //
  // Somebody did, and not on purpose: a factor row's pressed state was tracking
  // `expanded`, a state the reader had not touched, so the row someone had just
  // clicked gave no sign the panel had changed. Tracking the panel's highlight
  // instead fixed that and completed §13c's pair on the way through. It is
  // implemented here rather than left as a todo, and the mutation below is the
  // reason it is worth having as a test and not as a note.
  it("lights the factor whose key names the focused figure (spec §13c, direction two)", async () => {
    // Driven from a FIGURE, not from a row, so a `FactorList` that ignored the
    // panel's highlight fails here. And by `market` key, not by label or
    // position: `BAL` is the `spread` segment and `KC` the `moneyline` one, so a
    // row lit by its own headline order lights the wrong one and fails.
    const user = userEvent.setup();
    render(<ExplainerPanel {...RESTING} data={NFL} tiles={TILES} segments={SEGMENTS} />);
    await user.click(document.querySelector<HTMLElement>('[data-seg="BAL"]')!);
    expect(screen.getByTestId("factor-spread")).toHaveAttribute("data-highlighted", "true");
    expect(screen.getByTestId("factor-spread")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("factor-moneyline")).toHaveAttribute("data-highlighted", "false");
    expect(screen.getByTestId("factor-moneyline")).toHaveAttribute("aria-pressed", "false");
  });

  it("dims nothing at all when the factor names a market this panel has no figure for", async () => {
    // §13c's linkage is a LOOKUP: a factor names a `market` key and the figures
    // carrying that key light. A key that matches no tile and no segment has
    // nothing to look up, and it used to be forwarded anyway — which on a no-pick
    // panel is not a rare edge, it is every control such a panel has.
    // `template.py` always emits `record` (`:164`) and pads with `context`
    // (`:178`/`:184`), and neither is a market, so the reader clicked a row and
    // watched the whole panel fade to 0.4 with nothing lit anywhere: the only
    // evidence that they had done anything. Every existing highlight test starts
    // at `moneyline` or `spread`, and both have a tile, so the suite could not
    // see it.
    const user = userEvent.setup();
    const { container } = render(<ExplainerPanel {...RESTING} data={NO_PICK} tiles={TILES} segments={SEGMENTS} />);
    await user.click(screen.getByTestId("factor-record"));
    expect(dims(container)).toEqual(["1", "1"]);
    // And nothing is lit, so the row is not claiming a correspondence.
    expect(document.querySelector('[data-seg="BAL"]')).toHaveAttribute("data-highlighted", "false");
    expect(document.querySelector('[data-seg="KC"]')).toHaveAttribute("data-highlighted", "false");
    expect(screen.getByTestId("tile-total")).toHaveAttribute("data-highlighted", "false");
    expect(screen.getByTestId("factor-record")).toHaveAttribute("data-highlighted", "false");
  });

  it("presses the row the reader selected, and de-emphasises only what it did not light", async () => {
    // The other half, so the fix above cannot be "stop dimming": a key that DOES
    // resolve has to light the figure it names, press the row the reader just
    // pressed, and de-emphasise everything else. `data-highlighted` and
    // `aria-pressed` on a factor row used to track `expanded` — a different state
    // entirely, one the reader never touched on a wide panel — so the row the
    // reader had clicked gave no sign that the panel had changed at all.
    // `SEGMENTS` is crossed again: `BAL` is the `spread` segment, so a bar that
    // lit by position would dim `BAL` and light `KC` and fail here.
    const user = userEvent.setup();
    const { container } = render(<ExplainerPanel {...RESTING} data={NFL} tiles={TILES} segments={SEGMENTS} />);
    await user.click(screen.getByTestId("factor-spread"));
    expect(screen.getByTestId("factor-spread")).toHaveAttribute("data-highlighted", "true");
    expect(screen.getByTestId("factor-spread")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("factor-moneyline")).toHaveAttribute("data-highlighted", "false");
    expect(screen.getByTestId("factor-moneyline")).toHaveAttribute("aria-pressed", "false");
    expect(dims(container)).toEqual(["0.4", "1"]);
  });

  it("takes the light back down when the next row names nothing, so no row is a dead control", async () => {
    // What makes "do nothing" safe on a row whose key resolves to nothing. Left
    // alone it is the defect `SegmentFigure`'s comment is about: a focus stop
    // that announces itself and changes nothing. With this, every factor row
    // means one thing — light the figure this row is about, or clear the light
    // if there is none to light — so a row with no figure under its key turns a
    // light off, which is a state change the reader can see and undo.
    const user = userEvent.setup();
    const data: Common & Verdict = {
      ...NO_PICK,
      factors: [
        ...NO_PICK.factors,
        { key: "spread", direction: "down", headline: "The line asks more", text: "The market is asking for more." },
      ],
    };
    render(<ExplainerPanel {...RESTING} data={data} tiles={TILES} segments={SEGMENTS} />);
    await user.click(screen.getByTestId("factor-spread"));
    expect(screen.getByTestId("tile-spread")).toHaveAttribute("data-highlighted", "true");
    await user.click(screen.getByTestId("factor-record"));
    expect(screen.getByTestId("tile-spread")).toHaveAttribute("data-highlighted", "false");
    expect(screen.getByTestId("factor-spread")).toHaveAttribute("aria-pressed", "false");
  });

  it("reveals no figure the facts do not carry, whatever the reader does", async () => {
    // The named failure for §13c: a hover tooltip reading "probably around
    // 55-60%". Nothing may compute, round or interpolate — so this is a NEGATIVE
    // assertion on the rendered text, which is the only shape that failure takes.
    const user = userEvent.setup();
    const { container } = render(<ExplainerPanel {...RESTING} data={NFL} tiles={TILES} segments={SEGMENTS} record={{ label: "Picks made before kickoff", hits: 41, settled: 68 }} />);
    await user.click(screen.getByRole("button", { name: /model leans/i }));
    await user.tab();
    expect(container.textContent).not.toMatch(/\b\d+\s*[-\u2013]\s*\d+\s*%/);
  });

  it("shows the record strip and the player list through the panel, not just standalone", () => {
    // Found by rendering, not by a test: the strip was gated on the v1 branch,
    // so every v2 panel dropped it while the suite stayed green — because the
    // component test rendered RecordStrip directly and never through the panel.
    render(<ExplainerPanel {...RESTING} data={answer()} segments={SEGMENTS}
      record={{ label: "Picks made before kickoff", hits: 41, settled: 68 }}
      players={[{ name: "A. Tucker", projection: "71 rec yds" }]} />);
    expect(screen.getByText("Picks made before kickoff")).toBeInTheDocument();
    expect(screen.getByText("41/68")).toBeInTheDocument();
    expect(screen.getByText("A. Tucker")).toBeInTheDocument();
    expect(screen.getByText("71 rec yds")).toBeInTheDocument();
  });

  it("fails the footer closed: no model words without a model and a readable age", () => {
    for (const data of [
      answer({ model: "" }),
      answer({ generated_at: "not-a-date" }),
      answer({ source: "template" }),
    ]) {
      const { unmount } = render(<ExplainerPanel {...RESTING} data={data} />);
      expect(document.body.textContent).not.toMatch(/\bAI\b/);
      unmount();
    }
  });

  it("keeps a template answer visible rather than showing an error", () => {
    render(<ExplainerPanel {...RESTING} data={{ ...NFL, source: "template", model: "", verdict: "BAL is the pick.", factors: NFL.factors }} />);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("BAL is the pick.")).toBeInTheDocument();
  });

  it("hands the answer's pick to the bar, rather than letting the bar work it out", () => {
    // The pick is derived in Python (spec §5b) and travelled with the answer. A
    // panel that re-derived it would be a second definition of which side was
    // picked, which is the one thing that must not exist twice.
    const { container } = render(<ExplainerPanel {...RESTING} data={answer({ pick: { label: "BAL" } })} segments={NFL_BAR} />);
    expect(fills(container)).toEqual([NEUTRALS[0], ACCENT]);
  });

  it("accents nothing on a panel whose answer carries no pick", () => {
    const noPick = answer({
      verdict: "There is no pick for this one yet.",
      factors: [{ key: "context", direction: "neutral", headline: "Not much to go on", text: "The facts are still filling in." }],
    });
    const { container } = render(<ExplainerPanel {...RESTING} data={noPick} segments={NFL_BAR} />);
    expect(fills(container)).not.toContain(ACCENT);
    // Kevin's sentence, in full: nothing on a no-pick panel may say a row is
    // for or against a pick, in words or in colour.
    expect(document.body.textContent).not.toMatch(/for the pick|against it/i);
    expect(document.querySelector("svg[data-direction]")).toBeNull();
  });
});

/** Item 4, as a rule rather than as two string swaps. A machine key shown to a
 *  reader as if it were a label is the general defect; `btts` and `O2.5` are the
 *  two a screenshot happened to catch. The components render what a site hands
 *  them, so the only place a key or a bare `O` is actually *written* is the
 *  harness — the fixtures Kevin reads the panel from, and the shape every site's
 *  own mapping follows. It is read as source, because a string in a fixture that
 *  nothing renders today is still the string a site copies tomorrow.
 *
 *  **Parsed, not regexed.** This was a comment-strip plus regular expressions,
 *  which is a lint wearing a test's clothes: it cannot fail if the harness stops
 *  rendering the string, and it covers nothing about any real site, which is where
 *  a key would actually reach a reader. Worse, the comment-strip has no
 *  string-literal awareness, and a strip that is not literal-aware deletes *code*:
 *  one block-comment opener written inside a string pairs with the next closer
 *  anywhere in the file and takes a chunk of real source with it — including a
 *  `label: "btts"` — and the assertion then passes over a file that has the
 *  defect. So the file is parsed with the TypeScript compiler this package already
 *  depends on, which knows which characters are code, and the question becomes
 *  "what string does this property actually hold" rather than "does this text look
 *  like it would".
 */
describe("no raw key, and no bare O, reaches a reader", () => {
  const harness = readFileSync(resolve(__dirname, "../../harness/main.tsx"), "utf8");
  const parsed = ts.createSourceFile("main.tsx", harness, ts.ScriptTarget.ESNext, true, ts.ScriptKind.TSX);

  /** Every string the file actually contains: string literals, template
   *  literals with no interpolation, and JSX text. All three reach a reader; the
   *  old regex saw the first two by accident of how they happened to be written
   *  and the third only if it landed on one line. */
  function literals(): string[] {
    const out: string[] = [];
    const walk = (node: ts.Node) => {
      if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) out.push(node.text);
      else if (ts.isJsxText(node)) out.push(node.text);
      ts.forEachChild(node, walk);
    };
    walk(parsed);
    return out;
  }

  /** Object-literal `label` and `sub` values, which is where a raw key lands:
   *  `KeyNumberTile`'s label is the one slot on a tile reserved for words, and
   *  `sub` is the line beneath the figure. Both are read, so a tile whose `sub` is
   *  absent and which falls back to its label is caught either way. */
  function propertyWords(name: string): string[] {
    const out: string[] = [];
    const walk = (node: ts.Node) => {
      if (ts.isPropertyAssignment(node) && ts.isIdentifier(node.name) && node.name.text === name) {
        const init = node.initializer;
        if (ts.isStringLiteral(init) || ts.isNoSubstitutionTemplateLiteral(init)) out.push(init.text);
      }
      ts.forEachChild(node, walk);
    };
    walk(parsed);
    return out;
  }

  it("never hands a market key to a tile's label or to its sub line", () => {
    const labels = [...propertyWords("label"), ...propertyWords("sub")];
    for (const key of ["btts", "total_goals", "moneyline", "spread", "result"]) {
      // Compared as a value, not as a pattern: `label: "btts"` is the defect, and
      // `sub: "btts · 61%"` is a different string that happens to contain it, so
      // the check is equality and the diagnostic names the offending fixture.
      expect(labels, `a tile label or sub line holds the raw key "${key}"`).not.toContain(key);
    }
    // And the words that replaced them are there, so this is not a test that
    // passes by the fixtures having been emptied, or by the file having stopped
    // parsing into what we think it does.
    expect(labels).toContain("Both teams score");
    expect(labels).toContain("Over 2.5 · 56%");
  });

  it("never glues an O or a U to a digit, which is all 'O2.5' was", () => {
    // Why this is a rule about the TYPEFACE and not about the wording: Barlow's
    // zero is a plain oval, not slashed and not dotted, so a capital O and a
    // zero are near-identical outlines and the only thing that ever told them
    // apart was a space that was not there. Rendered in the real face at the
    // real 12px, "O2.5 56%" and "02.5 56%" are not distinguishable. A screen
    // reader saying "O two point five" has the same problem with no pixels
    // involved at all. The word fixes it; a separator alone does not, because
    // the whole string is one unbroken run of glyphs.
    for (const text of literals()) {
      expect(text, `"${text}" glues an O or a U to a digit`).not.toMatch(/[OU]\d/);
    }
  });
});

/** Item 5, decided: a rebuilt pick shows no band. The band is still computed and
 *  still in the response — `band_for` is untouched — because the claim is what
 *  is unsound, not the arithmetic. */
describe("a rebuilt pick's band", () => {
  it("shows the band when the pick was made in time", () => {
    render(<ExplainerPanel {...RESTING} data={answer({ band: "strong", pick_timing: "pre_kickoff" })} />);
    expect(screen.getByTestId("band-chip")).toHaveTextContent("Strong");
  });

  it("withholds it on a rebuilt pick, while the status line still says rebuilt", () => {
    // "STRONG" beside a disclosure that the pick was made after the start asks
    // the reader to resolve a contradiction the panel created, and a rebuilt
    // probability came from a model that had already seen the score. The pick
    // still counts (spec 2026-10-01-track-record-counts-every-pick); the band
    // is withheld because a confidence word about that number is the claim the
    // panel cannot make.
    const { container } = render(
      <ExplainerPanel {...RESTING} data={answer({ band: "strong", pick_timing: "rebuilt" })} segments={NFL_BAR} />,
    );
    expect(screen.queryByTestId("band-chip")).toBeNull();
    expect(container.textContent).not.toMatch(/strong/i);
    expect(screen.getByText("Made after kickoff")).toBeInTheDocument();
  });
});

/** §2 rule 3, and the one uncertainty in the verdict that failed **open**.
 *  Every other one fails closed, in this file and in the panel: `footer` drops
 *  the "AI" label on a blank model or a timestamp it cannot read, `KeyNumberTile`
 *  returns null for an absent market, `RecordStrip` shows a dash, `pct()`
 *  returns "—". The chip read `WORDS[band] ?? WORDS.moderate`, so a body with no
 *  `band` — or one carrying a word this build has never heard of — rendered
 *  **"Moderate"**: a specific confidence claim, derived from nothing, and derived
 *  by default, which is the same failure `band_for` exists to stop a model doing
 *  forty lines upstream. */
describe("a body the band cannot be read from", () => {
  /** The type says `band` is required and the wire does not promise it: a body
   *  that lost the field, a renamed value, a row the cache let through. The cast
   *  is the point — the type is the thing a renderer is tempted to trust in
   *  place of the value. */
  const bandless = (over: Record<string, unknown> = {}): Explanation =>
    ({ ...answer(), band: undefined, ...over }) as unknown as Explanation;

  it("shows no confidence word at all when the body carries no band", () => {
    render(<ExplainerPanel {...RESTING} data={bandless()} />);
    expect(screen.queryByTestId("band-chip")).toBeNull();
    // Not one word standing in for another. "Moderate" here is a claim about
    // this match that nothing in the response supports.
    expect(document.body.textContent).not.toMatch(/leaning|moderate|strong/i);
    // And the rest of the panel is unaffected: an answer we cannot read a band
    // out of is still an answer, and the verdict is the part the reader came
    // for. Fails closed on the claim, not on the panel.
    expect(screen.getByText(NFL.verdict)).toBeInTheDocument();
  });

  it("shows none for a band word this build has never heard of either", () => {
    // The same rule one step further out. `WORDS[band]` is undefined for any
    // value outside the union, and an unrecognised confidence is exactly as
    // unsayable as an absent one.
    render(<ExplainerPanel {...RESTING} data={bandless({ band: "certain" })} />);
    expect(screen.queryByTestId("band-chip")).toBeNull();
    expect(document.body.textContent).not.toMatch(/certain/i);
  });
});
