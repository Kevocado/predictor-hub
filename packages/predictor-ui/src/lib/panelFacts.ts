/** Shared v2 panelFacts adapter.
 *
 *  One function, two call sites.  Each call site passes an input tagged with
 *  `kind: "PL"` or `kind: "SP"`.  The function dispatches on that tag and
 *  returns a union output type.
 *
 *  PL input: `{ kind: "PL"; fixture: FixtureSummary }`
 *  SP input: `{ kind: "SP"; game: GameSummary; prediction: GamePrediction | null }`
 *
 *  PL output: `{ tiles: MarketTile[]; segments: Segment[]; legend: Segment[] | undefined }`
 *  SP output: `{ tiles: MarketTile[]; segments: Segment[]; legend: undefined }`
 *
 *  `news_date` is an optional field on the output, read from the service; when
 *  absent the footer element is omitted.  This task does not depend on Plan 1.
 */
import type { MarketTile, Segment } from "./predictor-ui";
import type {
  FixtureSummary,
  GameSummary,
  GamePrediction,
} from "../types";

/** PL three-way result shape — the adapter keeps `legend` when `implied` is present. */
interface PLInput {
  kind: "PL";
  fixture: FixtureSummary;
}
interface PLOutput {
  tiles: MarketTile[];
  segments: Segment[];
  legend: Segment[] | undefined;
}

/** Sports two-way moneyline + spread + total shape. */
interface SPInput {
  kind: "SP";
  game: GameSummary;
  prediction: GamePrediction | null;
}
interface SPOutput {
  tiles: MarketTile[];
  segments: Segment[];
  /** Sports never carries `implied`, so legend is always undefined here. */
  legend: undefined;
}

/** Union output — the callee selects the branch that matches its input. */
export type PanelFactsOutput = PLOutput | SPOutput;

/** Shared adapter — dispatch on the `kind` tag. */
export function panelFacts(
  input: PLInput
): PLOutput;
export function panelFacts(
  input: SPInput
): SPOutput;
export function panelFacts(
  input: PLInput | SPInput
): PanelFactsOutput {
  if (input.kind === "PL") {
    const { fixture } = input;
    const tiles: MarketTile[] = [];
    const segments: Segment[] = [];
    const legend: Segment[] = [];

    // --- PL three-way result ------------------------------------------------
    const known = [
      { key: "home_win", prob: fixture.home_win },
      { key: "draw", prob: fixture.draw },
      { key: "away_win", prob: fixture.away_win },
    ].filter((e): e is { prob: number } => e.prob !== null);

    if (known.length) {
      for (const e of known) {
        const label =
          e.key === "home_win"
            ? fixture.team_home
            : e.key === "away_win"
              ? fixture.team_away
              : "Draw";
        segments.push({ label, prob: e.prob, market: "result" });
        // Only add to legend when implied is present and the outcome is not draw.
        // The committed snapshot has implied === null for all 380 fixtures, so in
        // practice the row is omitted; the branch that draws it is the one that
        // needs a test, or it ships unexercised.
        if (e.key !== "draw" && fixture.implied !== null) {
          legend.push({ label, prob: fixture.implied, market: "result" });
        }
      }

      // lead outcome tile
      const lead = [...known].sort((a, b) => b.prob - a.prob)[0];
      const leadLabel =
        lead.key === "home_win"
          ? fixture.team_home
          : lead.key === "away_win"
            ? fixture.team_away
            : "Draw";
      tiles.push({
        market: "result",
        label: "result",
        value: Math.round(lead.prob * 100) / 100,
        sub: `win · ${leadLabel}`,
      });
    }

    // predicted_total_goals
    const total = fixture.predicted_total_goals;
    if (total !== null) {
      tiles.push({
        market: "total_goals",
        label: "total goals",
        value: Math.round(total * 10) / 10,
        sub: undefined,
      });
    }

    // btts_yes_prob
    const btts = fixture.btts_yes_prob;
    if (btts !== null) {
      tiles.push({
        market: "btts",
        label: "both score",
        value: Math.round(btts * 100) / 100,
        sub: undefined,
      });
    }

    return { tiles, segments, legend };
  }

  // --- Sports two-way moneyline + spread + total -------------------------
  if (input.kind === "SP") {
    const { game, prediction } = input;
    const tiles: MarketTile[] = [];
    const segments: Segment[] = [];

    if (prediction) {
      const home = typeof prediction.home_win_prob === "number"
        ? prediction.home_win_prob
        : null;
      const away = typeof prediction.away_win_prob === "number"
        ? prediction.away_win_prob
        : null;

      if (home !== null && away !== null) {
        // moneyline segments: home first (the order a fixture is written in)
        segments.push(
          { label: game.home_team, prob: home, market: "moneyline" },
          { label: game.away_team, prob: away, market: "moneyline" },
        );
        // leading-side tile
        const lead = home >= away
          ? { team: game.home_team, p: home }
          : { team: game.away_team, p: away };
        tiles.push({
          market: "moneyline",
          label: "moneyline",
          value: Math.round(lead.p * 100) / 100,
          sub: `win · ${lead.team}`,
        });
      }
    }

    // spread tile: needs BOTH the market's line and the model's own margin
    const spreadLine = typeof game.spread_line === "number" ? game.spread_line : null;
    const predictedMargin =
      typeof prediction?.predicted_margin === "number"
        ? prediction.predicted_margin
        : null;

    if (spreadLine !== null && predictedMargin !== null) {
      // The tile names the HOME team, always — per nflverse/CFB convention.
      // spread_line is the home team's expected margin (positive = home favored).
      // predicted_margin is home minus away. The tile value is the line,
      // and the sub-text carries the discrepancy.
      const discrepancy = Math.abs(predictedMargin - spreadLine);
      tiles.push({
        market: "spread",
        label: "spread",
        value: Math.abs(spreadLine),
        sub: `model +${discrepancy.toFixed(1)}`,
      });
    }

    // total_line
    const totalLine = typeof game.total_line === "number" ? game.total_line : null;
    const predictedTotal =
      typeof prediction?.predicted_total === "number"
        ? prediction.predicted_total
        : null;

    if (totalLine !== null && predictedTotal !== null) {
      tiles.push({
        market: "total_goals",
        label: "total goals",
        value: Math.round(predictedTotal),
        sub: `line ${totalLine}`,
      });
    }

    return { tiles, segments, legend: undefined };
  }

  // Fallback: return empty output
  return { tiles: [], segments: [], legend: undefined };
}
