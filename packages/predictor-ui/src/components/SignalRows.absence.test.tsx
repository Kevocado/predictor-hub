/**
 * `absence_strip` — phase 2's visual, and the reason Phase 2 was blocked for
 * every sport at once.
 *
 * Until now this package REFUSED `absence_strip` outright: `FIGURE` mapped it to
 * `null`, so `signalFigure` raised `UndrawableSignalVisualError` and no absence
 * signal could be drawn anywhere. That refusal was correct while it was true —
 * rendering the words with no marker is the failure the existing refusal tests
 * exist to prevent — and it became false the moment the visual was built, so the
 * refusal and the visual had to land together.
 *
 * ## What it draws, and why the `n >= 30` floor does NOT apply
 *
 * The figure is the **player's own projection** — 78 rush yards for NFL, a
 * scoring probability for PL. It is a claim about *this* fixture and *this*
 * player, exactly like the `delta_chip`'s disagreement, which `rateIsDrawable`
 * already exempts "because the figures it draws are this game's own".
 *
 * So `DRAWS_A_RATE.absence_strip` is `false`, and that is load-bearing rather
 * than convenient: for an absence row `n` is a **count of players**, not a count
 * of graded observations. Applying the floor would refuse a row for having fewer
 * than 30 injured players, which is a category error — and would be a floor
 * invented for the wrong quantity, on a signal that is not a rate at all.
 *
 * ## What the marker is, and what it is not
 *
 * A plain number in the sport's own units, unsigned. Not a percentage: a
 * percentage would assert the figure is a share, which is true for PL's scoring
 * probability and false for NFL's yards, and the component cannot know which
 * sport it is drawing. The unit belongs in the headline, which already has to
 * state the figure.
 *
 * Not coloured `pr-win`/`pr-loss` either. A player being out is not an outcome
 * the model got right or wrong, and the sign/direction rule in this package is
 * that direction is never carried by colour.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  SignalRows,
  SPEC_MIN_N,
  UndrawableSignalVisualError,
  rateIsDrawable,
  signalFigure,
  type Signal,
} from "./SignalRows";

/** A phase-2 absence row: the player's own projection, in the sport's units. */
const absence = (over: Partial<Signal> = {}): Signal => ({
  kind: "absence",
  sport: "nfl",
  game_id: "2026_04_KC_BAL",
  headline: {
    // The spec's own wording (\u00a74), and note that it STATES the figure --
    // `assertFigureIsStated` refuses a row whose words do not carry what its
    // marker draws, which is the whole point of the component.
    text: "Out: J. Jacobs, our #2 rush projection (78 yds)",
    figures: { projection: 78 },
  },
  n: 3,
  source: "ESPN injury report, Wed",
  as_of: "2026-10-03T16:44:10Z",
  strength: 0.4,
  pre_kickoff_only: true,
  visual: "absence_strip",
  ...over,
});

describe("absence_strip", () => {
  it("draws, rather than being refused", () => {
    expect(() => render(<SignalRows signals={[absence()]} />)).not.toThrow();
    expect(screen.getByText(/Out: J\. Jacobs/)).toBeInTheDocument();
  });

  it("names its own figure", () => {
    expect(signalFigure(absence(), "absence_strip")).toBe(78);
  });

  it("draws the projection as a plain unsigned number in the sport's units", () => {
    render(<SignalRows signals={[absence()]} />);
    // Not "78%", because a percentage asserts the figure is a share — true for
    // PL's scoring probability, false for NFL's yards.
    expect(screen.getByTestId("signal-absence")).toHaveTextContent("78");
  });

  it("states the figure its marker draws", () => {
    // The whole point of the component: a figure on the page that the row's own
    // words do not carry is a 500, not a warning.
    render(<SignalRows signals={[absence()]} />);
    expect(screen.getByTestId("signal-headline")).toHaveTextContent("78");
  });

  it("refuses a headline that does not state the figure it draws", () => {
    expect(() =>
      render(<SignalRows signals={[absence({ headline: { text: "A player is out", figures: { projection: 78 } } })]} />),
    ).toThrow(/draws "absence_strip"|headline/i);
  });

  it("is exempt from the n >= 30 floor, because its n counts players", () => {
    // The load-bearing decision. `n` here is a count of injured players, not of
    // graded observations; applying the rate floor would refuse a row for having
    // fewer than 30 injuries, which is a category error.
    expect(rateIsDrawable(absence({ n: 1 }), SPEC_MIN_N)).toBe(true);
    expect(rateIsDrawable(absence({ n: null }), SPEC_MIN_N)).toBe(true);
  });

  it("is not painted as a rate", () => {
    // A bar would claim a hit-rate reading the figure does not support.
    const { container } = render(<SignalRows signals={[absence()]} />);
    expect(container.querySelector('[data-testid="signal-bar"]')).toBeNull();
  });

  it("carries no colour that says the model was right or wrong", () => {
    // Being out is not an outcome. Direction is never carried by colour in this
    // package, and an absence is not an outcome at all.
    const { container } = render(<SignalRows signals={[absence()]} />);
    const marker = container.querySelector('[data-testid="signal-absence"]');
    expect(marker?.className ?? "").not.toMatch(/pr-win|pr-loss/);
  });

  it("still refuses projected_vs_actual, which is phase 3", () => {
    expect(() =>
      render(<SignalRows signals={[absence({ kind: "post_game", visual: "projected_vs_actual" })]} />),
    ).toThrow(UndrawableSignalVisualError);
  });

  it("handles a fractional projection without inventing precision", () => {
    render(<SignalRows signals={[absence({ headline: { text: "Out: Saka, our #2 midfielder, 62% to score", figures: { projection: 62 } } })]} />);
    expect(screen.getByTestId("signal-absence")).toHaveTextContent("62");
  });
});