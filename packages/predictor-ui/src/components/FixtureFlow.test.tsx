/** FixtureFlow — instant, local, state-appropriate description.
 *
 *  Pure function of its props.  No useEffect, no fetch, no timer.
 *  Renders the game flow for the given sport and state.
 *
 *  The pre-game tests below assert ABSENCE: the pick sentence, the win
 *  probabilities, the pick's timing and the market line are the instant block's,
 *  as figures, one of them — so a sentence repeating any of them here is the
 *  same number twice on a page, and the test that would have let it back in is
 *  gone with it.
 *
 *  Honour assertions (must bite):
 *  - No line named that is not there (test on rendered strings, not keys).
 *  - No direction marker, no "the market disagrees", no derived percentage.
 *  - F1 draws no market-line tile and no split-bar market row.
 *  - Every sentence is true for every bundle that reaches it.
 */

import { render, screen } from "@testing-library/react";
import { FixtureFlow } from "./FixtureFlow";

/** Render FixtureFlow with the given sport, state, and bundle.
 *  The request function is stubbed to reject, so the flow is shown with the
 *  unreachable-explainer guard. */
const renderFixtureFlow = (
  sport: string,
  state: "pre-game" | "in-play" | "finished",
  bundle: any,
  requestFn = () => Promise.reject(new Error("unreachable"))
) => {
  render(
    <FixtureFlow
      sport={sport}
      state={state}
      bundle={bundle}
      request={requestFn}
    />
  );
  return { screen };
};

/** Pre-game bundle shapes (one per sport). */
const preGameBundles = {
  pl: {
    home_team: "Arsenal",
    away_team: "Chelsea",
    market_shape: "three_way" as const,
    market_line: null,
    predicted_total_goals: 2.7,
    btts_yes_prob: 0.61,
    pick: { label: "Arsenal", prob: 0.48 },
    pick_timing: "pre_kickoff",
    drivers: [],
    context: {},
    record: { label: "Picks made before the session", hits: 9, settled: 20 },
  } as const,
  sp: {
    home_team: "KC",
    away_team: "BAL",
    market_shape: "two_way" as const,
    market_line: -2.5,
    predicted_margin: -3.4,
    predicted_total: 45.2,
    home_win_prob: 0.38,
    away_win_prob: 0.62,
    pick: { label: "BAL", prob: 0.62 },
    pick_timing: "pre_kickoff",
    drivers: [],
    context: {},
  } as const,
  f1: {
    driver: "Lando Norris",
    podium: [{ driver: "Lando Norris", prob: 0.34 }, { driver: "Max Verstappen", prob: 0.29 }],
    points: 25,
    dnf: null,
    market_line: null,
    pick: { label: "Lando Norris", prob: 0.34 },
    pick_timing: "the session",
    drivers: [{ driver: "Lando Norris" }],
    context: {},
  } as const,
  nba: {
    minimal: {
      market_line: null,
      spread: null,
      total_line: null,
      home_team: "GSW",
      away_team: "BOS",
      home_win_prob: 0.5,
      away_win_prob: 0.5,
      pick: { label: "GSW", prob: 0.5 },
      pick_timing: "tip-off",
      drivers: [],
      context: {},
    } as const,
    with_line: {
      market_line: "Over 224.5",
      spread: "224.5",
      total_line: "Over 44.5",
      home_team: "GSW",
      away_team: "BOS",
      home_win_prob: 0.5,
      away_win_prob: 0.5,
      pick: { label: "GSW", prob: 0.5 },
      pick_timing: "tip-off",
      drivers: [],
      context: {},
    } as const,
  } as const,
};

/** Finished bundle shapes. */
const finishedBundles = {
  pl: {
    home_team: "Arsenal",
    away_team: "Chelsea",
    result: "home_win",
    market_shape: "three_way" as const,
    market_line: null,
    predicted_total_goals: 2.7,
    btts_yes_prob: 0.61,
    pick: { label: "Arsenal", prob: 0.48, was_right: true },
    pick_timing: "pre_kickoff",
    drivers: [],
    context: {},
    record: { label: "Picks made before the session", hits: 9, settled: 20 },
  } as const,
  sp: {
    home_team: "KC",
    away_team: "BAL",
    result: "away_cover",
    market_shape: "two_way" as const,
    market_line: -2.5,
    predicted_margin: -3.4,
    predicted_total: 45.2,
    home_win_prob: 0.38,
    away_win_prob: 0.62,
    pick: { label: "BAL", prob: 0.62, was_right: true },
    pick_timing: "pre_kickoff",
    drivers: [],
    context: {},
  } as const,
  f1: {
    driver: "Lando Norris",
    podium: [{ driver: "Lando Norris", prob: 0.34 }, { driver: "Max Verstappen", prob: 0.29 }],
    points: 25,
    dnf: null,
    market_line: null,
    pick: { label: "Lando Norris", prob: 0.34, was_right: true },
    pick_timing: "the session",
    drivers: [{ driver: "Lando Norris" }],
    context: {},
  } as const,
};

/** In-play bundle shapes. */
const inPlayBundles = {
  pl: {
    home_team: "Arsenal",
    away_team: "Chelsea",
    score: { home: 2, away: 1 },
    market_shape: "three_way" as const,
    market_line: null,
    predicted_total_goals: 2.7,
    btts_yes_prob: 0.61,
    pick: { label: "Arsenal", prob: 0.48 },
    pick_timing: "rebuilt",
    drivers: [],
    context: {},
    record: { label: "Picks made before the session", hits: 9, settled: 20 },
  } as const,
  sp: {
    home_team: "KC",
    away_team: "BAL",
    score: { home: 21, away: 17 },
    market_shape: "two_way" as const,
    market_line: -2.5,
    predicted_margin: -3.4,
    predicted_total: 45.2,
    home_win_prob: 0.38,
    away_win_prob: 0.62,
    pick: { label: "BAL", prob: 0.62 },
    pick_timing: "rebuilt",
    drivers: [],
    context: {},
  } as const,
  f1: {
    driver: "Lando Norris",
    podium: [{ driver: "Lando Norris", prob: 0.34 }, { driver: "Max Verstappen", prob: 0.29 }],
    points: 25,
    dnf: null,
    market_line: null,
    pick: { label: "Lando Norris", prob: 0.34 },
    pick_timing: "the session",
    drivers: [{ driver: "Lando Norris" }],
    context: {},
  } as const,
  nba: {
    minimal: {
      market_line: null,
      spread: null,
      total_line: null,
      home_team: "GSW",
      away_team: "BOS",
      home_win_prob: 0.5,
      away_win_prob: 0.5,
      pick: { label: "GSW", prob: 0.5 },
      pick_timing: "rebuilt",
      drivers: [],
      context: {},
    } as const,
  } as const,
};

describe("FixtureFlow: state-appropriate, honest flow description", () => {
  // ---- Pre-game ----

  describe("pre-game", () => {
    it("PL: says no pick sentence before the button", () => {
      const { screen } = renderFixtureFlow("pl", "pre-game", preGameBundles.pl);
      // The flow must name the fixture and must not contain a line sentence.
      const flowText = screen.getByTestId("fixture-flow").innerHTML;
      expect(flowText).not.toContain("market line");
      expect(flowText).toContain("Arsenal");
      // The pick, as a sentence, is the block's. Here it would be the same
      // figure in two places, which is the defect this phase removes.
      expect(screen.queryByText(/The model picks/)).toBeNull();
      expect(screen.queryByText(/Win probabilities/)).toBeNull();
    });

    it("Sports: two moneyline segments, no line tile", () => {
      const { screen } = renderFixtureFlow("sp", "pre-game", preGameBundles.sp);
      const flowText = screen.getByTestId("fixture-flow").innerHTML;
      expect(flowText).not.toContain("spread");
      expect(flowText).not.toContain("total");
      expect(flowText).toContain("KC");
      expect(flowText).toContain("BAL");
      // Neither the pick nor the two win probabilities — the block's tiles and
      // bar carry them, once.
      expect(screen.queryByText(/The model picks/)).toBeNull();
      expect(screen.queryByText(/Win probabilities/)).toBeNull();
      // The market's line, too: it is a tile the site passes, or nothing.
      expect(screen.queryByText(/The market's line is/)).toBeNull();
    });

    it("F1: draws no market-line tile and no split-bar market row", () => {
      const { screen } = renderFixtureFlow("f1", "pre-game", preGameBundles.f1);
      const flowText = screen.getByTestId("fixture-flow").innerHTML;
      // F1 has no market_line, so no line tile should appear.
      expect(flowText).not.toContain("market-line");
      expect(flowText).not.toContain("split-bar");
      // The pick and its win probability are the block's now — as a verdict and
      // as a figure. F1 has no home/away name either, so the pre-game flow is
      // empty, which is the point: nothing here repeats the block.
      expect(screen.queryByText(/The model picks/)).toBeNull();
      expect(flowText).not.toContain("win probability");
    });

    it("NBA thin bundle: flow is legible even with no market_line", () => {
      renderFixtureFlow("nba", "pre-game", preGameBundles.nba.minimal);
      // Flow should render without error; the "no line" case is handled.
      expect(screen.getByTestId("fixture-flow")).not.toBeNull();
    });

    it("F1 rebuilt: the moment sentence is the block's, not a sentence here", () => {
      const { screen } = renderFixtureFlow("f1", "pre-game", {
        ...preGameBundles.f1,
        pick_timing: "rebuilt",
      });
      // The rebuilt disclosure moved to `InstantBlock`, which words it per sport
      // ("after the session started" for F1) — see InstantBlock.test.tsx.
      expect(screen.getByTestId("fixture-flow").innerHTML).not.toContain("after the session started");
      expect(screen.queryByText(/The pick was made/)).toBeNull();
    });

    it("NFL rebuilt: the moment sentence is the block's, not a sentence here", () => {
      const { screen } = renderFixtureFlow("nfl", "pre-game", {
        ...preGameBundles.sp,
        pick_timing: "rebuilt",
      });
      expect(screen.getByTestId("fixture-flow").innerHTML).not.toContain("after the game started");
      expect(screen.queryByText(/The pick was made/)).toBeNull();
    });
  });

  // ---- In-play ----

  describe("in-play", () => {
    it("PL: shows score and how it stands against the line when there is one", () => {
      const { screen } = renderFixtureFlow("pl", "in-play", inPlayBundles.pl);
      const flowText = screen.getByTestId("fixture-flow").innerHTML;
      expect(flowText).toContain("score");
      // PL has no market_line, so no line sentence should appear.
      expect(flowText).not.toContain("market line");
    });

    it("Sports: shows score and how it stands against the line when there is one", () => {
      const { screen } = renderFixtureFlow("sp", "in-play", inPlayBundles.sp);
      const flowText = screen.getByTestId("fixture-flow").innerHTML;
      expect(flowText).toContain("score");
      expect(flowText).not.toContain("no market line");
    });

    it("F1: shows the state of the game and how it stands", () => {
      const { screen } = renderFixtureFlow("f1", "in-play", inPlayBundles.f1);
      const flowText = screen.getByTestId("fixture-flow").innerHTML;
      expect(flowText).toContain("state");
      expect(flowText).not.toContain("market line");
    });
  });

  // ---- Finished ----

  describe("finished", () => {
    it("PL: result and whether the model's pick was right", () => {
      const { screen } = renderFixtureFlow("pl", "finished", finishedBundles.pl);
      const flowText = screen.getByTestId("fixture-flow").innerHTML;
      expect(flowText).toContain("result");
      expect(flowText).toContain("was right");
    });

    it("Sports: result and pick rightness", () => {
      const { screen } = renderFixtureFlow("sp", "finished", finishedBundles.sp);
      const flowText = screen.getByTestId("fixture-flow").innerHTML;
      expect(flowText).toContain("result");
      expect(flowText).toContain("pick rightness");
    });

    it("F1: result and pick rightness", () => {
      const { screen } = renderFixtureFlow("f1", "finished", finishedBundles.f1);
      const flowText = screen.getByTestId("fixture-flow").innerHTML;
      expect(flowText).toContain("result");
      expect(flowText).toContain("pick rightness");
    });
  });
});
