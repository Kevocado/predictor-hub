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
});
