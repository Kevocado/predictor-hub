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
import { pct } from "../fmt";
import {
  SignalRows,
  SPEC_MIN_N,
  MAX_HEADLINE_WORDS,
  clipHeadline,
  rateIsDrawable,
  signalIsDrawn,
  UndrawableSignalVisualError,
  SignalFigureError,
  HeadlineFigureMismatchError,
  headlineStatesFigure,
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

  /* RED-CHECK 4a — "a headline that states a different figure", the case the
   * Major names: "Backed by 61% of 30 picks" beside a drawn 74%. */
  it("REFUSES a headline that states a DIFFERENT figure than the one it draws", () => {
    // The exact shape: the payload's `rate` is 0.738 and the words say 61%. Both
    // are in the signal, the bar would draw at 73.8%, and on `origin/main` before
    // this fix nothing objected — because a 12-word headline skipped the only
    // branch that looked at the figures.
    expect(() =>
      render(
        <SignalRows
          signals={[trust({ headline: { text: "Backed by 61% of 30 picks.", figures: { rate: 0.738 } } })]}
        />,
      ),
    ).toThrow(HeadlineFigureMismatchError);
    expect(() =>
      render(
        <SignalRows
          signals={[trust({ headline: { text: "Backed by 61% of 30 picks.", figures: { rate: 0.738 } } })]}
        />,
      ),
    ).toThrow(/61% of 30 picks/);
  });

  it("REFUSES a chip row whose headline omits its gap too", () => {
    expect(() =>
      render(<SignalRows signals={[lineGap({ headline: { text: "The model disagrees with the line.", figures: { gap: 1.6 } } })]} />),
    ).toThrow(HeadlineFigureMismatchError);
  });

  /* RED-CHECK 4b — a matching short headline must survive untouched. */
  it("a short headline that AGREES renders, unchanged and unclipped", () => {
    render(<SignalRows signals={[trust()]} />);
    const headline = screen.getByTestId("signal-headline");
    expect(headline).toHaveAttribute("data-clipped", "false");
    expect(headline.textContent).toBe("At 72% this model has been right 74% of the time.");
    expect(screen.getByTestId("signal-bar-fill")).toHaveStyle({ width: "73.8%" });
  });

  /* RED-CHECK 4c — an omitted figure. */
  it("REFUSES a headline that OMITS the figure entirely", () => {
    // Not a contradiction: the words simply never mention it. A bar with no
    // number beside it is a bare figure with no sample size in words, which is the
    // reader-facing outcome the rule exists to prevent.
    expect(() =>
      render(<SignalRows signals={[trust({ headline: { text: "This model has a graded record.", figures: { rate: 0.738 } } })]} />),
    ).toThrow(HeadlineFigureMismatchError);
  });

  it("accepts every word a headline may legitimately use for the figure", () => {
    // The punctuation, sign and boundary forms, through the real component, so
    // the validator and the clipper cannot be tightened into rejecting real copy
    // — each of these was refused by some version of this rule.
    // `[text, rate]`, paired explicitly rather than inferred from the text: an
    // inference would pick the rate from the very string under test, so the case
    // would assert whatever the inference decided rather than what the component
    // does with a fixed payload.
    const accepted: [string, number][] = [
      ["At 72% this model has been right 74% of the time.", 0.738],
      ["Right 74%.", 0.738],                // trailing full stop
      ["Right (74%) of its picks.", 0.738], // parenthetical
      ["Right +74% here.", 0.738],          // leading sign
      ["The 74% case.", 0.738],             // sentence-initial
      ["Right <1% here.", 0.004],           // the formatter's own form
      ["Right 0% here.", 0.004],            // and the plain word for the same rate
      ["Right 100% here.", 0.996],          // and the top boundary
      ["Right >99% here.", 0.996],          // and the formatter's form for it
      // 4172215627: a figure glued to a word by an em dash. Whitespace splitting
      // used to leave `74%—based` as one token and refuse a headline that plainly
      // states the figure.
      ["Right 74%—based on 42 games, all of them.", 0.738],
    ];
    for (const [text, rate] of accepted) {
      const { unmount } = render(
        <SignalRows signals={[trust({ n: 42, headline: { text, figures: { rate } } })]} />,
      );
      expect(screen.getByTestId("signal-row"), text).toBeInTheDocument();
      unmount();
    }
  });

  it("figureForms and headlineStatesFigure, as functions", () => {
    // `0.738` draws at 74% (`pct`) and floors to 73%, and both are accepted
    // because a headline at that boundary legitimately says either. Asserted
    const bar = (rate: number) => trust({ headline: { text: "", figures: { rate } } });
    const chip = (gap: number) => lineGap({ headline: { text: "", figures: { gap } } });
    const says = (text: string, s: Signal, figure: number) => headlineStatesFigure(text, s, figure);

    // The ordinary middle: `pct` rounds to 74% and a writer may say 73%.
    expect(says("right 74% of the time", bar(0.738), 0.738)).toBe(true);
    expect(says("right 73% of the time", bar(0.738), 0.738)).toBe(true);
    expect(says("right 61% of the time", bar(0.738), 0.738)).toBe(false);
    // A percent and a bare number are different quantities.
    expect(says("wants 1.6 more here", bar(0.738), 0.738)).toBe(false);
    expect(says("right 74 here", bar(0.738), 0.738)).toBe(false);

    // `1%` never satisfies `61%`, in either direction, because the unit of
    // comparison is the NUMBER.
    expect(says("right 61% here", bar(0.01), 0.01)).toBe(false);
    expect(says("right 1% here", bar(0.61), 0.61)).toBe(false);

    // 4172215627: internal punctuation. Whitespace splitting used to leave
    // `74%—based` as one token and refuse a headline that plainly states 74%.
    expect(says("Right 74%—based on 42 games, all of them here", bar(0.738), 0.738)).toBe(true);
    expect(says("74%,74%,74% and 74% in a row", bar(0.738), 0.738)).toBe(true);

    // 4172215626: the boundary symbol is part of the claim. `<1%` means less
    // than one percent, so `1%` states a rate the bar does not draw.
    expect(says("Right <1% here", bar(0.004), 0.004)).toBe(true);
    expect(says("Right 1% here", bar(0.004), 0.004)).toBe(false);
    // A boundaryless 0% is consistent with `<1%` and is accepted.
    expect(says("Right 0% here", bar(0.004), 0.004)).toBe(true);
    expect(says("Right >99% here", bar(0.996), 0.996)).toBe(true);
    expect(says("Right 100% here", bar(0.996), 0.996)).toBe(true);
    // `99%` with no comparator is the value AT the bound, which `>99%` denies —
    // the mirror of `1%` under `<1%`, and the same reason. Asserted because the
    // tempting "round both sides and stop" fix passes the `<1%` case and fails
    // this one.
    expect(says("Right 99% here", bar(0.996), 0.996)).toBe(false);
    // And the wrong boundary is refused in both directions.
    expect(says("Right >1% here", bar(0.004), 0.004)).toBe(false);
    expect(says("Right <99% here", bar(0.996), 0.996)).toBe(false);
    // A boundary with no drawn boundary is a hedge this component cannot check.
    expect(says("Right <74% here", bar(0.738), 0.738)).toBe(false);

    // 4172215630: a gap's sign is the direction. The chip reads +1.6, so -1.6 is
    // the opposite claim. An unsigned 1.6 is prose, not a contradiction.
    expect(says("wants 1.6 more", chip(1.6), 1.6)).toBe(true);
    expect(says("wants +1.6 more", chip(1.6), 1.6)).toBe(true);
    expect(says("wants \u22121.6 more", chip(1.6), 1.6)).toBe(false);
    expect(says("wants \u22121.6 more", chip(-1.6), -1.6)).toBe(true);
    expect(says("wants +1.6 more", chip(-1.6), -1.6)).toBe(false);
    // A rate has no direction, so a sign on it is not a contradiction.
    expect(says("right +74% here", bar(0.738), 0.738)).toBe(true);
  });

  it("a refusal takes the WHOLE list down, before any row renders", () => {
    // The cost of throwing, asserted rather than described: no half-drawn list.
    expect(() =>
      render(<SignalRows signals={[trust(), lineGap({ headline: { text: "No gap named.", figures: { gap: 1.6 } } })]} />),
    ).toThrow(HeadlineFigureMismatchError);
    expect(screen.queryByTestId("signal-row")).not.toBeInTheDocument();
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

/* ---------------------------------------------------------------------------
 * The `n`-floor interaction, made deliberate rather than incidental.
 *
 * The order in `signalIsDrawn` is floor-then-validate, so a below-floor rate is
 * DROPPED and never validated: its figure is suppressed and its headline goes
 * with it, so there is nothing on the page for the figure to contradict. The
 * alternative — validating first — would make every sub-floor bucket a thrown
 * error, and a sport with twelve games of history could not render its panel at
 * all. Spec §4 says a sub-floor rate says nothing, and "nothing" is not a crash.
 * ------------------------------------------------------------------------- */

describe("the floor interaction · a dropped row is not a contradicted row", () => {
  it("DROPS, does not reject, a below-floor rate whose headline omits its figure", () => {
    // The case that settles the order. If validation ran first this would throw,
    // and a sport early in its record would lose its whole panel over a row that
    // was never going to draw.
    const { container } = render(
      <SignalRows
        signals={[trust({ n: 12, headline: { text: "Too few games to say.", figures: { rate: 8 / 12 } } })]}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("drops a below-floor rate whose headline states a DIFFERENT figure too", () => {
    // Same verdict for the same reason, and deliberately: the row renders nothing,
    // so there is no figure on the page to disagree with anything.
    const { container } = render(
      <SignalRows
        signals={[trust({ n: 12, headline: { text: "Backed by 90% of 12 picks.", figures: { rate: 0.02 } } })]}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("STILL rejects the same bad headline once `n` clears the floor", () => {
    // The floor is the only thing suppressing the earlier case. Above it, the
    // headline is on the page and the figure is beside it, so they must agree.
    expect(() =>
      render(<SignalRows signals={[trust({ n: 30, headline: { text: "Backed by 90% of 12 picks.", figures: { rate: 0.02 } } })]} />),
    ).toThrow(HeadlineFigureMismatchError);
  });

  it("a `delta_chip` row with n = null is validated like any other row", () => {
    // No floor applies to a gap, so there is no suppression to hide behind: the
    // check runs on every render path or it runs on none.
    expect(() =>
      render(<SignalRows signals={[lineGap({ n: null, headline: { text: "The model disagrees.", figures: { gap: 1.6 } } })]} />),
    ).toThrow(HeadlineFigureMismatchError);
    const { unmount } = render(<SignalRows signals={[lineGap({ n: null })]} />);
    expect(screen.getByTestId("signal-row")).toBeInTheDocument();
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

  // RED-CHECK: only the token normalised, the protected form left raw —
// "2 failed | 41 passed (43)".
it("matches a boundary symbol on BOTH sides, so `<1%` matches itself", () => {
  // CodeRabbit review comment 4171902960. `bare` stripped the token's angle
  // bracket while the protected form kept its own, so the DRAWN boundary rate
  // stopped matching itself and was clipped.
  for (const rate of [0.004, 0.996]) {
    const late =
      `Across every stored pre-kickoff pick in this bucket here the model was right ` +
      `${pct(rate)} of the time across the whole season's record so far.`;
    expect(late.split(" ").findIndex((w) => w.startsWith(pct(rate)))).toBeGreaterThan(MAX_HEADLINE_WORDS);
    const { unmount } = render(
      <SignalRows signals={[trust({ headline: { text: late, figures: { rate } } })]} />,
    );
    expect(screen.getByTestId("signal-headline").textContent).toContain(pct(rate));
    unmount();
  }
});

it("matches a SIGNED figure in the text against an unsigned protected form", () => {
  // The same finding, on a gap: a headline that writes "+1.6" must still match
  // the protected `1.6`, since the sign is the direction and not part of the
  // number.
  const late = "Across this whole season the model has wanted +1.6 more than the market on this one.";
  render(<SignalRows signals={[lineGap({ headline: { text: late, figures: { gap: 1.6 } } })]} />);
  const headline = screen.getByTestId("signal-headline");
  expect(headline).toHaveAttribute("data-clipped", "true");
  expect(headline.textContent).toContain("+1.6");
  expect(screen.getByTestId("signal-delta")).toHaveTextContent("+1.6");
});

// RED-CHECK: `norm` stripping no leading punctuation —
// "2 failed | 43 passed (45)".
it("matches a figure wrapped in OPENING punctuation, past the cap", () => {
  // CodeRabbit review comment 4171924918: `norm("(74%")` returned `(74%` while the
  // protected form normalised to `74%`, so the drawn figure was clipped away.
  const late =
    "Across every stored pre-kickoff pick this season the model has been right " +
    "(74% of the time in this bucket of settled games) with the margin called";
  const { unmount } = render(
    <SignalRows signals={[trust({ headline: { text: late, figures: { rate: 0.738 } } })]} />,
  );
  const headline = screen.getByTestId("signal-headline");
  expect(headline).toHaveAttribute("data-clipped", "true");
  expect(headline.textContent).toContain("74%");
  unmount();

  // And through the real component, where the protected forms are the drawn
  // ones. `(1.6` must sit past the cap or this passes for the wrong reason —
  // CodeRabbit's nitpick on the previous version of this case, which had it at
  // word 7 where the plain 12-word clip keeps it anyway. Asserted on the index.
  const gapLate =
    "Across every stored pick this season the model has wanted more than the line " +
    "(1.6 points of margin every single week of the schedule so far)";
  expect(gapLate.split(" ").findIndex((w) => w.startsWith("(1.6"))).toBeGreaterThan(MAX_HEADLINE_WORDS);
  const { unmount: u2 } = render(
    <SignalRows signals={[lineGap({ headline: { text: gapLate, figures: { gap: 1.6 } } })]} />,
  );
  const gapHeadline = screen.getByTestId("signal-headline");
  expect(gapHeadline).toHaveAttribute("data-clipped", "true");
  expect(gapHeadline.textContent).toContain("(1.6");
  expect(screen.getByTestId("signal-delta")).toHaveTextContent("+1.6");
  u2();
});

it("counts the cap on ordinary words, so a protected one does not spend it", () => {
    // The stated cost: a clipped row may exceed 12 words, and the cap is on the
    // sentence around the figure rather than on the figure.
    const out = clipHeadline("a b c 74% d e f g h i j k l m n", 4, (w) => w.includes("74%"));
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
    // Protection is a PREDICATE the caller supplies, so these cases exercise the
    // clipper's own arithmetic (which words are kept, in what order) rather than
    // how a figure is recognised — that is `headlineStatesFigure`'s test above,
    // and `SignalRow` wires the two together.
    // With no predicate this is the plain 12-word clip it has always been.
    expect(clipHeadline("a b 74% c", 2, (w) => w.includes("74%"))).toEqual({ text: "a b 74%", clipped: true });
    // A protected form that appears nowhere drops nothing and changes nothing.
    expect(clipHeadline("a b c d", 2, (w) => w.includes("99%"))).toEqual({ text: "a b", clipped: true });
    // Surrounding punctuation is not part of the figure, so a sentence-final
    // "74%." is still the protected word.
    expect(clipHeadline("a b 74%. c d", 2, (w) => w.startsWith("74%"))).toEqual({ text: "a b 74%.", clipped: true });
    // A PARENTHESIS closes too, which is the shape a "(74% of 61 games)" aside
    // takes.
    expect(clipHeadline("a b 74%) d e", 2, (w) => w.startsWith("74%"))).toEqual({ text: "a b 74%)", clipped: true });
    // The predicate is asked about the raw word, so it sees whatever the writer
    // typed. That is the whole point of the change: recognising a figure is
    // `headlineStatesFigure`'s job and it scans the text for NUMBERS rather than
    // normalising words.
    expect(clipHeadline("a b +1.6 d e", 2, (w) => w === "+1.6")).toEqual({ text: "a b +1.6", clipped: true });
    expect(clipHeadline("a b <1% d e", 2, (w) => w === "<1%")).toEqual({ text: "a b <1%", clipped: true });
    expect(clipHeadline("a b <1% d e", 2, (w) => w.includes("1%"))).toEqual({ text: "a b <1%", clipped: true });
    expect(clipHeadline("a b −2.5 d e", 2, (w) => w.includes("2.5"))).toEqual({ text: "a b −2.5", clipped: true });
    // An opening bracket is not part of the figure, so a predicate reading the
    // raw word still recognises `(74%` — the scanner in `headlineStatesFigure`
    // is what makes that work, and 4171924918 is what asked for it.
    expect(clipHeadline("a b (74% d e", 2, (w) => w.includes("74%"))).toEqual({ text: "a b (74%", clipped: true });
    expect(clipHeadline("a b [74%] d e", 2, (w) => w.includes("74%"))).toEqual({ text: "a b [74%]", clipped: true });
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