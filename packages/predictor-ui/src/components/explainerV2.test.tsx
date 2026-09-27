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
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ExplainerPanel, FactorList, KeyNumberTile, RecordStrip } from "../index";
import { ProbabilityBar } from "./ProbabilityBar";
import type { Explanation, MarketTile, Segment } from "../index";

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
    render(<ProbabilityBar segments={[{ label: "A", prob: 0.97 }, { label: "B", prob: 0.03 }]} minSegmentPx={2} />);
    const seg = document.querySelector<HTMLButtonElement>('[data-seg="B"]')!;
    expect(seg).toHaveTextContent("3%");
    seg.focus();
    expect(seg).toHaveFocus();
    // The sliver is the FILL's job: the label is text and never shrinks.
    expect(document.querySelector('[data-testid="pbar-fill"][data-min-width]')).toBeTruthy();
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
    const user = userEvent.setup();
    render(<ExplainerPanel {...RESTING} data={NFL} tiles={TILES} segments={SEGMENTS} />);
    await user.click(screen.getByRole("button", { name: /the line asks more/i }));
    expect(screen.getByTestId("tile-spread")).toHaveAttribute("data-highlighted", "true");
    expect(document.querySelector('[data-seg="BAL"]')).toHaveAttribute("data-highlighted", "true");
    await user.keyboard("{Escape}");
    expect(screen.getByTestId("tile-spread")).toHaveAttribute("data-highlighted", "false");
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
 */
describe("no raw key, and no bare O, reaches a reader", () => {
  // Comments are stripped first: this repo explains a rule by quoting the code it
  // replaced, so the literal strings "btts" and "O2.5" appear in prose that is
  // documentation, not output. The strip is line- and block-comment removal with
  // no string-literal awareness, which is safe here because this one file has no
  // `//` inside a string.
  const harness = readFileSync(resolve(__dirname, "../../harness/main.tsx"), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");

  it("never hands a market key to a tile's label or to its sub line", () => {
    for (const key of ["btts", "total_goals", "moneyline", "spread", "result"]) {
      expect(harness, key).not.toMatch(new RegExp(`(?:label|sub):\\s*"${key}"`));
    }
    // And the words that replaced them are there, so this is not a test that
    // passes by the fixtures having been emptied.
    expect(harness).toMatch(/label:\s*"Both teams score"/);
    expect(harness).toMatch(/sub:\s*"Over 2\.5 · 56%"/);
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
    expect(harness).not.toMatch(/[OU]\d/);
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
    // "STRONG" beside "shown for reference and not counted" asks the reader to
    // resolve a contradiction the panel created, and a rebuilt probability came
    // from a model that had already seen the score.
    const { container } = render(
      <ExplainerPanel {...RESTING} data={answer({ band: "strong", pick_timing: "rebuilt" })} segments={NFL_BAR} />,
    );
    expect(screen.queryByTestId("band-chip")).toBeNull();
    expect(container.textContent).not.toMatch(/strong/i);
    expect(screen.getByText("Rebuilt after kickoff")).toBeInTheDocument();
  });
});
