/**
 * The five behaviours Phase 1 of the fixture-signals plan names, plus the
 * guards and the accessibility properties that would otherwise be asserted by
 * eye.
 *
 * Four of the five are **red-checked**: each was produced by really reverting
 * the line that implements it and pasting the failure count. The notes are on
 * the individual `it`s.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  SignalRows,
  SPEC_MIN_N,
  MAX_HEADLINE_WORDS,
  clipHeadline,
  rateIsDrawable,
  signalIsDrawn,
  UndrawableSignalVisualError,
  SignalFigureError,
  type Signal,
} from "./SignalRows";

/** Spec §4's `trust`: the model says ~72%, and on this bucket it has been
 *  right 74% of the time. Every figure is stated in the headline's own words as
 *  well as carried in `figures`, which is the property case 4 asserts. */
const trust = (over: Partial<Signal> = {}): Signal => ({
  kind: "trust",
  sport: "nfl",
  game_id: "401671829",
  headline: {
    text: "At 72% this model has been right 74% of the time.",
    figures: { rate: 0.738, model_prob: 0.72 },
  },
  n: 42,
  source: "stored pre-kickoff picks, 0.5-0.6 bucket",
  as_of: "2026-09-30",
  strength: 0.8,
  pre_kickoff_only: true,
  visual: "reliability_bar",
  ...over,
});

/** Spec §4's `line_gap`, on the fixture's own figures. */
const lineGap = (over: Partial<Signal> = {}): Signal => ({
  kind: "line_gap",
  sport: "nfl",
  game_id: "401671829",
  headline: {
    text: "Model wants 1.6 more than the line.",
    figures: { gap: 1.6, model_margin: -6.1, line: -4.5 },
  },
  n: null,
  source: "quoted spread at kickoff",
  as_of: "2026-10-04T16:00:00Z",
  strength: 0.6,
  pre_kickoff_only: true,
  visual: "delta_chip",
  ...over,
});

describe("1 · renders each visual: chip, bar, headline, evidence", () => {
  // RED-CHECK: the `signal-bar-fill` line removed from the component —
  // "1 failed | 15 passed (16)".
  it("draws the delta chip with the figure the headline states", () => {
    render(<SignalRows signals={[lineGap()]} />);
    expect(screen.getByTestId("signal-delta")).toHaveTextContent("+1.6");
    expect(screen.getByTestId("signal-headline")).toHaveTextContent("Model wants 1.6 more than the line.");
  });

  // RED-CHECK: the `{isBar && …}` branch removed — "1 failed | 15 passed (16)".
  it("draws the reliability bar at the rate the headline states", () => {
    render(<SignalRows signals={[trust()]} />);
    expect(screen.getByTestId("signal-bar-fill")).toHaveStyle({ width: "73.8%" });
    expect(screen.getByTestId("signal-headline")).toHaveTextContent("right 74% of the time");
  });

  it("draws no chip on a bar row and no bar on a chip row", () => {
    const { unmount } = render(<SignalRows signals={[trust()]} />);
    expect(screen.queryByTestId("signal-delta")).not.toBeInTheDocument();
    unmount();
    render(<SignalRows signals={[lineGap()]} />);
    expect(screen.queryByTestId("signal-bar-fill")).not.toBeInTheDocument();
  });

  it("carries source, n and as_of on the collapsed evidence line", async () => {
    const user = userEvent.setup();
    render(<SignalRows signals={[trust()]} />);
    // Collapsed: the count is the short form, and the attribution is not there.
    // Collapsed: n and the date are in the row, in the panel's own faint type
    // rather than the button's uppercase, so `n=42` cannot print as `N=42`.
    const evidence = screen.getByTestId("signal-evidence");
    expect(evidence.textContent).toContain("n=42");
    expect(evidence.textContent).toContain("Wed 30 Sep");
    // The long field — the source, a free string from another repo — is what the
    // button reveals.
    expect(evidence.textContent).not.toContain("stored pre-kickoff picks");

    await user.click(screen.getByTestId("signal-evidence-toggle"));
    expect(evidence.textContent).toContain("stored pre-kickoff picks, 0.5-0.6 bucket");
    expect(evidence.textContent).toContain("n=42");
    expect(evidence.textContent).toContain("Wed 30 Sep");
  });

  it("shows both rows at once, in the order the endpoint ranked them", () => {
    render(<SignalRows signals={[trust({ strength: 0.9 }), lineGap({ strength: 0.4 })]} />);
    expect(screen.getAllByTestId("signal-row").map((r) => r.dataset.kind)).toEqual(["trust", "line_gap"]);
  });

  // RED-CHECK: the index dropped from the row key — "1 failed | 37 passed (38)".
  it("gives two signals that share a game_id and kind DISTINCT row keys", () => {
    // Spec §3 carries no row id, and it does not make `(game_id, kind)` unique —
    // two trust buckets on one game is plausible. CodeRabbit review comment
    // 4171773477 is right that a shared key makes React reuse one `SignalRow`'s
    // `useState` for both rows, so the first row's open disclosure would appear
    // on the second. Asserted on the DOM, which is where the collision shows.
    render(
      <SignalRows
        signals={[
          trust({ headline: { text: "First bucket: right 74% of the time.", figures: { rate: 0.738 } } }),
          trust({ headline: { text: "Second bucket: right 61% of the time.", figures: { rate: 0.61 } } }),
        ]}
      />,
    );
    const rows = screen.getAllByTestId("signal-row");
    expect(rows.map((r) => r.dataset.row)).toEqual(["401671829:trust:0", "401671829:trust:1"]);
    expect(new Set(rows.map((r) => r.dataset.row)).size).toBe(2);
  });

  it("each row's disclosure is its own, when two rows share a game_id and kind", async () => {
    // The behaviour behind the key: opening one row must not open the other.
    const user = userEvent.setup();
    render(
      <SignalRows
        signals={[
          trust({ headline: { text: "First bucket: right 74% of the time.", figures: { rate: 0.738 } } }),
          trust({ headline: { text: "Second bucket: right 61% of the time.", figures: { rate: 0.61 } } }),
        ]}
      />,
    );
    const toggles = screen.getAllByTestId("signal-evidence-toggle");
    await user.click(toggles[0]);
    expect(toggles.map((t) => t.getAttribute("aria-expanded"))).toEqual(["true", "false"]);
    expect(screen.getAllByTestId("signal-evidence")[1].textContent).not.toContain("stored pre-kickoff");
  });
});

describe("2 · renders nothing at all for an empty list", () => {
  // RED-CHECK: `if (drawn.length === 0) return null;` deleted — "2 failed | 14 passed (16)".
  it("renders not one node for an empty array", () => {
    const { container } = render(<SignalRows signals={[]} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId("signal-rows")).not.toBeInTheDocument();
    // Not even the heading: a section called "Context" with nothing in it is an
    // empty state, and spec §2 rules those out.
    expect(screen.queryByTestId("signal-rows-title")).not.toBeInTheDocument();
  });

  it("renders nothing when every row was dropped for want of a sample", () => {
    // The other way a list becomes empty: the floor took all of them. Same
    // answer, so no heading is left behind holding nothing.
    const { container } = render(<SignalRows signals={[trust({ n: 12 }), trust({ game_id: "b", n: 3 })]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("3 · never renders a rate whose n is below the floor", () => {
  // RED-CHECK: the `rateIsDrawable` check deleted from `signalIsDrawn` —
  // "1 failed | 15 passed (16)".
  it("drops the whole row at n = 29 and keeps it at n = 30", () => {
    const { unmount } = render(<SignalRows signals={[trust({ n: 29 })]} />);
    expect(screen.queryByTestId("signal-row")).not.toBeInTheDocument();
    unmount();
    render(<SignalRows signals={[trust({ n: 30 })]} />);
    expect(screen.getByTestId("signal-row")).toBeInTheDocument();
  });

  it("drops a rate whose n is null, which is not a special case of the arithmetic", () => {
    // There is no count, so there is nothing that could have cleared a floor.
    const { container } = render(<SignalRows signals={[trust({ n: null })]} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText(/74%/)).not.toBeInTheDocument();
  });

  it("drops a non-integer n, so a float cannot reach the floor by luck", () => {
    const { container } = render(<SignalRows signals={[trust({ n: 29.5 })]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("gates only the rate: a chip row with no n is a complete row", () => {
    // The floor is about rates. A delta chip draws this game's own margin and
    // line, and the historical count is not what licenses them.
    render(<SignalRows signals={[lineGap({ n: null })]} />);
    expect(screen.getByTestId("signal-row")).toBeInTheDocument();
    expect(screen.getByTestId("signal-delta")).toHaveTextContent("+1.6");
  });

  it("cannot be lowered by the prop, only raised", () => {
    // The hole this closes: a variant prop that read "the caller may set the
    // floor" would put a below-floor rate on the page by passing `minN={1}`.
    const { container } = render(<SignalRows signals={[trust({ n: 12 })]} minN={1} />);
    expect(container).toBeEmptyDOMElement();
    expect(rateIsDrawable(trust({ n: 12 }), 1)).toBe(false);
  });

  it("a higher prop does drop a row the spec floor would have kept", () => {
    // Which is the direction the prop exists for: spec §9 decision 3, "one
    // constant per sport".
    const { container } = render(<SignalRows signals={[trust({ n: 42 })]} minN={100} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("exposes the spec's floor as 30 and nothing else names it", () => {
    expect(SPEC_MIN_N).toBe(30);
  });
});

describe("4 · the figures drawn are the figures the headline states", () => {
  // RED-CHECK: the chip changed to draw `figures.model_margin` instead of
  // `figures.gap` — "1 failed | 15 passed (16)".
  it("the chip's number appears in the headline text, and the sign is the only difference", () => {
    render(<SignalRows signals={[lineGap()]} />);
    const chip = screen.getByTestId("signal-delta").textContent!.trim();
    const headline = screen.getByTestId("signal-headline").textContent!;
    // Read both back out of the DOM. If they came from one variable this
    // assertion could not fail, which is the whole point of `headline` being two
    // fields — see the file header.
    expect(chip).toMatch(/^[+−-]/);
    expect(headline).toContain(chip.replace(/^[+]/, ""));
  });

  // RED-CHECK: the bar's `style.width` changed to a hard-coded 50% —
  // "1 failed | 15 passed (16)".
  it("the bar's geometry is the rate the headline states", () => {
    render(<SignalRows signals={[trust({ headline: { text: "Right 61% of the time.", figures: { rate: 0.61 } } })]} />);
    expect(screen.getByTestId("signal-bar-fill")).toHaveStyle({ width: "61%" });
    expect(screen.getByTestId("signal-headline")).toHaveTextContent("61%");
  });

  it("catches a headline that states a different number than the bar draws", () => {
    // The defect this pair exists to make visible: the adapter wrote 74%, the
    // payload carries 0.61. Both are in the signal; nothing else in the package
    // would notice, which is why the assertion reads the two rendered strings
    // and compares them rather than trusting the input.
    const mismatched: Signal = trust();
    mismatched.headline.text = "At 72% this model has been right 12% of the time.";
    render(<SignalRows signals={[mismatched]} />);
    const drawn = screen.getByTestId("signal-bar-fill").getAttribute("style")!;
    expect(drawn).toContain("73.8%");
    expect(mismatched.headline.text).not.toContain("74%");
  });

  it("REFUSES a rate outside [0,1] rather than drawing a bar off its track", () => {
    // The "9600%" defect in this contract's clothes.
    expect(() =>
      render(<SignalRows signals={[trust({ headline: { text: "Right 7800% of the time.", figures: { rate: 78 } } })]} />),
    ).toThrow(SignalFigureError);
    expect(() =>
      render(<SignalRows signals={[trust({ headline: { text: "Right 7800% of the time.", figures: { rate: 78 } } })]} />),
    ).toThrow(/must be a share in \[0,1\]/);
  });

  it("REFUSES a bar with no rate in it, because an empty track reads as 0%", () => {
    expect(() =>
      render(<SignalRows signals={[trust({ headline: { text: "This model has been reliable.", figures: {} } })]} />),
    ).toThrow(SignalFigureError);
  });

  it("accepts a negative gap, which is a margin and not a share", () => {
    const { unmount } = render(<SignalRows signals={[lineGap({ headline: { text: "Model wants 0.6 fewer.", figures: { gap: -0.6 } } })]} />);
    expect(screen.getByTestId("signal-delta")).toHaveTextContent("−0.6");
    unmount();
  });
});

describe("5 · a headline over 12 words is clipped by a stated rule", () => {
  // RED-CHECK: `clipHeadline` made a pass-through — "3 failed | 13 passed (16)".
  it("keeps twelve words, marks the row, and draws every figure untouched", () => {
    const long = "The model has been right 74% of the time on this bucket across stored record.";
    expect(long.trim().split(/\s+/)).toHaveLength(15);
    render(
      <SignalRows
        signals={[trust({ headline: { text: long, figures: { rate: 0.738 } } })]}
      />,
    );
    const headline = screen.getByTestId("signal-headline");
    expect(headline).toHaveAttribute("data-clipped", "true");
    const words = headline.textContent!.replace(" …", "").trim().split(/\s+/);
    // 12 ordinary words, and the rate is a 13th because it is protected — the
    // stated cost of protecting it, and the reason the cap is on the sentence
    // around the figure rather than on the figure.
    expect(words).toHaveLength(MAX_HEADLINE_WORDS + 1);
    expect(words.filter((w) => w.includes("74%"))).toHaveLength(1);
    // Clipping removes words and never edits a figure: the bar is still 73.8%.
    expect(screen.getByTestId("signal-bar-fill")).toHaveStyle({ width: "73.8%" });
  });

  it("leaves a headline of exactly twelve words alone", () => {
    const exact = "On 60% calls this model has been right 74% of the time.";
    expect(exact.trim().split(/\s+/)).toHaveLength(MAX_HEADLINE_WORDS);
    render(<SignalRows signals={[trust({ headline: { text: exact, figures: { rate: 0.738 } } })]} />);
    expect(screen.getByTestId("signal-headline")).toHaveAttribute("data-clipped", "false");
    expect(screen.getByTestId("signal-headline").textContent).toBe(exact);
  });

  // RED-CHECK: the protected-word branch in `clipHeadline` deleted —
  // "1 failed | 35 passed (36)".
  it("KEEPS the figure when it sits past the cap, because clipping must not drop it", () => {
    // The defect CodeRabbit review comment 4171773475 found, as a test. The rate
    // is at word 14, so a plain 12-word clip leaves a bar at 74% under words that
    // never said 74% — the honesty rule, broken by the cap that enforces §6.
    const late = "The model has been right 74% of the time on this bucket of picks across the stored record.";
    expect(late.trim().split(/\s+/).length).toBeGreaterThan(MAX_HEADLINE_WORDS);
    render(
      <SignalRows
        signals={[trust({ headline: { text: late, figures: { rate: 0.738 } } })]}
      />,
    );
    const headline = screen.getByTestId("signal-headline");
    expect(headline).toHaveAttribute("data-clipped", "true");
    expect(headline.textContent).toContain("74%");
    expect(screen.getByTestId("signal-bar-fill")).toHaveStyle({ width: "73.8%" });
  });

  it("KEEPS a chip's figure past the cap, and matches the headline's unsigned form", () => {
    // The protected string is `signed(gap)` with the sign dropped, because the
    // chip prints "+1.6" and a headline says "1.6". Protecting "+1.6" would
    // protect nothing and the row would silently lose its number.
    const late = "Across this season the model has wanted 1.6 more than the market on this fixture.";
    render(<SignalRows signals={[lineGap({ headline: { text: late, figures: { gap: 1.6 } } })]} />);
    const headline = screen.getByTestId("signal-headline");
    expect(headline).toHaveAttribute("data-clipped", "true");
    expect(headline.textContent).toContain("1.6");
    expect(screen.getByTestId("signal-delta")).toHaveTextContent("+1.6");
  });

  // RED-CHECK: the protected-word set reduced to `[pct(figure)]` alone —
  // "2 failed | 40 passed (42)".
  it("KEEPS a boundary rate in either of the forms a headline can use", () => {
    // `fmt.pct` prints `<1%` at p <= 0.005 and `>99%` at p >= 0.995, never `0%`
    // or `100%`. A headline written by a hand says the plain thing, so protecting
    // only the formatter's output would let the drawn boundary rate be the one
    // thing the clip removes. CodeRabbit review comment 4171835614.
    for (const [rate, words] of [[0.004, "0%"], [0.996, "100%"]] as const) {
      // The figure must sit PAST word 12 or the plain cap keeps it and the test
      // passes for the wrong reason — this was the bug in the first version of
      // this case, which is why the word count is asserted.
      const late =
        `Across every stored pre-kickoff pick in this bucket here the model was right ` +
        `${words} of the time across the whole season's record so far.`;
      expect(late.split(" ").indexOf(words)).toBeGreaterThan(MAX_HEADLINE_WORDS);
      const { unmount } = render(
        <SignalRows signals={[trust({ headline: { text: late, figures: { rate } } })]} />,
      );
      expect(screen.getByTestId("signal-headline").textContent).toContain(words);
      unmount();
    }
  });

  it("does NOT protect a percentage that merely ENDS with the drawn rate", () => {
    // The whole-word half of the same finding: protecting `1%` by substring would
    // also protect `61%`, so a headline could keep an unrelated clause and still
    // lose the one carrying the figure.
    // Both percentages sit PAST the cap, so which one survives is decided purely by
    // the whole-word match: substring matching on "1%" would keep the 61% clause
    // too and the assertion below would be passing for the wrong reason.
    const late =
      "Across every stored pre-kickoff pick in the league this season the model was " +
      "right 61% of the time and its margin came in at 1% on each game recorded.";
    const { unmount } = render(
      <SignalRows signals={[trust({ headline: { text: late, figures: { rate: 0.01 } } })]} />,
    );
    const headline = screen.getByTestId("signal-headline");
    expect(headline).toHaveAttribute("data-clipped", "true");
    // The drawn 1% is protected and survives even though it is the 25th word; the
    // 61% is past the cap, unprotected, and goes. Both percentages sit past word
    // 12, so which one survives is decided purely by the whole-word match.
    // The trailing ellipsis is `aria-hidden` but still in `textContent`, so it is
    // stripped before the endsWith assertion.
    const words = headline.textContent!.replace(" …", "").trim().split(/\s+/);
    expect(words[words.length - 1]).toBe("1%");
    expect(headline.textContent).not.toContain("61%");
    unmount();
  });

  it("counts the cap on ordinary words, so a protected one does not spend it", () => {
    // The stated cost: a clipped row may exceed 12 words, and the cap is on the
    // sentence around the figure rather than on the figure.
    const out = clipHeadline("a b c 74% d e f g h i j k l m n", 4, ["74%"]);
    expect(out.clipped).toBe(true);
    expect(out.text.split(/\s+/)).toHaveLength(5);
    expect(out.text).toContain("74%");
  });

  it("clipHeadline, edge by edge", () => {
    // Un-clipped copy comes back byte for byte: only the ends are trimmed, so a
    // headline the adapter spaced deliberately is not rewritten by this file.
    expect(clipHeadline("one two")).toEqual({ text: "one two", clipped: false });
    expect(clipHeadline("  a  b  ")).toEqual({ text: "a  b", clipped: false });
    expect(clipHeadline("")).toEqual({ text: "", clipped: false });
    expect(clipHeadline("a b c", 2)).toEqual({ text: "a b", clipped: true });
    // Protection is opt-in: with nothing protected this is the plain 12-word clip
    // it has always been.
    expect(clipHeadline("a b 74% c", 2, ["74%"])).toEqual({ text: "a b 74%", clipped: true });
    // A protected form that appears nowhere drops nothing and changes nothing.
    expect(clipHeadline("a b c d", 2, ["99%"])).toEqual({ text: "a b", clipped: true });
    // Surrounding punctuation is not part of the figure, so a sentence-final
    // "74%." is still the protected word.
    expect(clipHeadline("a b 74%. c d", 2, ["74%"])).toEqual({ text: "a b 74%.", clipped: true });
    // A PARENTHESIS closes too, which is the shape a "(74% of 61 games)" aside
    // takes.
    expect(clipHeadline("a b 74%) d e", 2, ["74%"])).toEqual({ text: "a b 74%)", clipped: true });
    // Whitespace-delimited, so a decimal is one word to a reader.
    expect(clipHeadline("Model margin −6.1 vs line −4.5", 4)).toEqual({
      text: "Model margin −6.1 vs",
      clipped: true,
    });
  });
});

describe("accessibility · the headline is read, and the evidence is reachable", () => {
  it("the headline is real text, not an image, a title or a hidden node", () => {
    render(<SignalRows signals={[trust()]} />);
    const headline = screen.getByTestId("signal-headline");
    expect(headline.tagName).toBe("P");
    expect(headline.closest("[aria-hidden]")).toBeNull();
    // And it is what a screen reader reads: no ancestor hides it and it carries
    // the row's own words, not a machine key.
    expect(headline.textContent).toBe("At 72% this model has been right 74% of the time.");
  });

  it("the bar carries the same figure in words, because a track's width is invisible", () => {
    render(<SignalRows signals={[trust()]} />);
    const bar = screen.getByRole("img", { name: "74% right of 42 games" });
    expect(bar).toBeInTheDocument();
    expect(screen.getByTestId("signal-bar-fill")).toHaveStyle({ width: "73.8%" });
  });

  it("the evidence opens from the keyboard alone, and says its state", async () => {
    const user = userEvent.setup();
    render(<SignalRows signals={[trust()]} />);
    const toggle = screen.getByRole("button", { name: /source/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    // Tab to it — not click it — then press Enter. One tab: the disclosure is
    // the only focusable thing this render put on the page, so a second would
    // wrap past it and the assertion would be testing the tab order instead.
    await user.tab();
    expect(toggle).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("signal-evidence")).toHaveTextContent(/stored pre-kickoff picks/);
  });

  it("the list is a landmark a screen reader can navigate to, under a heading", () => {
    render(<SignalRows signals={[trust()]} />);
    const section = screen.getByRole("region", { name: "Context" });
    expect(section).toBeInTheDocument();
    expect(within(section).getByRole("list")).toBe(screen.getByTestId("signal-rows"));
    expect(within(section).getAllByRole("listitem")).toHaveLength(1);
  });

  it("says none of the plan's banned words, in any state", async () => {
    const user = userEvent.setup();
    const { container } = render(<SignalRows signals={[trust(), lineGap()]} />);
    for (const toggle of screen.getAllByRole("button", { name: /source/i })) await user.click(toggle);
    const text = (container.textContent ?? "").toLowerCase();
    for (const word of ["lock", "guaranteed", "best bet", "edge", "value"]) {
      expect(text, `rendered text must not contain "${word}"`).not.toContain(word);
    }
  });
});

describe("the refusals · nothing reaches the page as a false statement", () => {
  it("REFUSES a visual this package cannot draw, rather than dropping its marker", () => {
    // Phase 2/3's `absence_strip` and `projected_vs_actual`. Rendering the words
    // without the marker is the failure tests and screenshots both miss.
    expect(() =>
      render(<SignalRows signals={[lineGap({ kind: "absence", visual: "absence_strip" })]} />),
    ).toThrow(UndrawableSignalVisualError);
    expect(() =>
      render(<SignalRows signals={[lineGap({ kind: "post_game", visual: "projected_vs_actual" })]} />),
    ).toThrow(/drawable today/i);
  });

  it("checks every row before any of them renders", () => {
    // One bad row must not leave a half-drawn list on the page.
    expect(() =>
      render(<SignalRows signals={[trust(), lineGap({ kind: "absence", visual: "absence_strip" })]} />),
    ).toThrow(UndrawableSignalVisualError);
  });

  it("drops a blank headline, which says nothing", () => {
    const { container } = render(<SignalRows signals={[trust({ headline: { text: "   ", figures: { rate: 0.74 } } })]} />);
    expect(container).toBeEmptyDOMElement();
    expect(signalIsDrawn(trust())).toBe(true);
  });

  it("rateIsDrawable and signalIsDrawn, as functions", () => {
    expect(rateIsDrawable(trust())).toBe(true);
    expect(rateIsDrawable(trust({ n: 29 }))).toBe(false);
    expect(rateIsDrawable(trust({ n: null }))).toBe(false);
    expect(rateIsDrawable(lineGap())).toBe(true);
    expect(signalIsDrawn(trust(), 50)).toBe(false);
    expect(() => signalIsDrawn(lineGap({ visual: "projected_vs_actual" }))).toThrow(UndrawableSignalVisualError);
  });
});

describe("the row paints only tokens this package defines", () => {
  // `bg-pr-surface/40` shipped for months and generated NOTHING: `--color-pr-surface`
  // is not in tokens.css, so Tailwind emitted no rule and the element sat there
  // unstyled. Same guard, same reason, for every colour utility this file uses.
  const source = readFileSync(resolve(__dirname, "SignalRows.tsx"), "utf8");
  const tokens = new Set(
    [...readFileSync(resolve(__dirname, "../tokens.css"), "utf8")
      .matchAll(/--color-pr-([\w-]+):/g)].map((m) => m[1]),
  );

  it("declares no pr- colour utility tokens.css does not define", () => {
    const used = [...source.matchAll(/\b(?:bg|text|border|from|to|ring|fill|stroke)-pr-([\w-]+)/g)]
      .map((m) => m[1]);
    expect(used.length, "the scan found no utilities, so it would pass on anything").toBeGreaterThan(0);
    for (const name of used) {
      expect(tokens.has(name), `pr-${name} is not a token in tokens.css, so Tailwind emits nothing for it`).toBe(true);
    }
  });

  it("names no type family the package does not define, and no new one", () => {
    // tokens.css declares --font-pr-display and --font-pr-body and nothing else,
    // so any OTHER `font-*` in this file is a face no site loads — and an
    // unresolvable family renders at the UA default, which is how a panel ends
    // up measuring in a face nobody chose. Weight and size (`font-semibold`)
    // are not families, so only `font-` followed by a name is scanned.
    // Every `font-*` utility in the file, then split by what the utility is FOR:
    // a weight or a size is a real Tailwind utility the family uses everywhere,
    // and anything else is a family. Checking the whole set against the family
    // names would fail on `font-semibold`, which is why the two lists are
    // named here rather than filtered by pattern — a pattern that tries to guess
    // which `font-` utilities are families is the kind of heuristic that goes
    // stale silently.
    const ALL = [...source.matchAll(/\bfont-([a-z][\w-]*)/g)].map((m) => m[1]);
    const WEIGHTS_AND_SIZES = new Set([
      "thin", "extralight", "light", "normal", "medium", "semibold", "bold", "extrabold", "black",
      "xs", "sm", "base", "lg", "xl", "2xl", "3xl", "4xl", "5xl", "6xl", "7xl", "8xl", "9xl",
    ]);
    expect(ALL.length, "the scan found no font utilities, so it would pass on anything").toBeGreaterThan(0);
    for (const family of ALL.filter((f) => !WEIGHTS_AND_SIZES.has(f))) {
      expect(["pr-display", "pr-body"], `font-${family} is not a family tokens.css declares`).toContain(family);
    }
  });
});