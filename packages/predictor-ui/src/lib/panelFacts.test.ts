/** Shared v2 panelFacts adapter — tests.
 *
 *  One test per distinct behaviour from the two live adapters (PL + Sports),
 *  including cases where they differ.  A case that passes against both
 *  implementations is not evidence of anything; a case where they differ
 *  is the valuable one, and it is marked with a comment.
 *
 *  All inputs provide `kind: "PL"` or `kind: "SP"` so the adapter can dispatch.
 */

import { describe, expect, it } from "vitest";

import { panelFacts } from "./panelFacts";
import type { MarketTile, Segment } from "../predictor-ui";
import type { FixtureSummary } from "../types";

/** ---- PL FIXTURES ---- */

/** Base PL fixture with full data. */
const plBase = (): FixtureSummary => ({
  event_id: "gw1",
  commence_time: "2026-11-08T15:00:00Z",
  team_home: "Arsenal",
  team_away: "Chelsea",
  home_win: 0.48,
  draw: 0.26,
  away_win: 0.26,
  over_2_5: 0.56,
  under_2_5: 0.44,
  btts_yes_prob: 0.61,
  top_scoreline: "2-1",
  predicted_result: "home_win",
  draw_signal: false,
  is_fallback_prediction: false,
  data_confidence: "established",
  predicted_total_goals: 2.7,
  predicted_margin: 0.4,
  home_2plus_prob: 0.58,
  away_2plus_prob: 0.5,
  value_bet_flags: [],
} as FixtureSummary);

/** PL: three segments + legend empty (implied null). */
it("PL: three segments + legend empty when implied null", () => {
  const { tiles, segments, legend } = panelFacts({
    kind: "PL" as const,
    fixture: plBase(),
  });
  expect(segments.map((s) => `${s.label} ${s.prob}`)).toEqual([
    "Arsenal 0.48", "Draw 0.26", "Chelsea 0.26",
  ]);
  expect(tiles.map((t) => `${t.market}:${t.value}`)).toEqual(["result:48%", "total_goals:2.7", "btts:61%"]);
  expect(tiles[0].sub).toBe("win · Arsenal");
  expect(legend).toEqual([]);
});

/** PL: legend has 2 entries when implied carries on two outcomes. */
it("PL: legend has 2 entries when implied carries on two outcomes", () => {
  const { legend } = panelFacts({
    kind: "PL" as const,
    fixture: {
      ...plBase(),
      home_win: { prob: 0.48, implied: 0.44, edge: null as any },
      away_win: { prob: 0.26, implied: 0.3, edge: null as any },
    } as unknown as FixtureSummary,
  });
  expect(legend).toHaveLength(2);
});

/** PL: legend has 3 entries when implied carries on all three. */
it("PL: legend has 3 entries when implied carries on all three outcomes", () => {
  const { legend } = panelFacts({
    kind: "PL" as const,
    fixture: {
      ...plBase(),
      home_win: { prob: 0.48, implied: 0.44, edge: null as any },
      draw: { prob: 0.26, implied: 0.25, edge: null as any },
      away_win: { prob: 0.26, implied: 0.31, edge: null as any },
    } as unknown as FixtureSummary,
  });
  expect(legend.map((s) => s.label)).toEqual(["Arsenal", "Draw", "Chelsea"]);
});

/** PL: no fixture → empty tiles + segments. */
it("PL: no fixture returns empty tiles and segments", () => {
  const { tiles, segments } = panelFacts({
    kind: "PL" as const,
    fixture: null as unknown as FixtureSummary,
  });
  expect(tiles).toEqual([]);
  expect(segments).toEqual([]);
});

/** PL: result tile with sub "win · <lead label>" when known outcomes. */
it("PL: result tile sub names the lead outcome", () => {
  const { tiles } = panelFacts({
    kind: "PL" as const,
    fixture: plBase(),
  });
  expect(tiles[0].sub).toBe("win · Arsenal");
});

/** PL: omit btts tile when btts_yes_prob is null. */
it("PL: omit btts tile when btts_yes_prob is null", () => {
  const noBtts = {
    ...plBase(),
    btts_yes_prob: null,
  } as unknown as FixtureSummary;
  const { tiles } = panelFacts({ kind: "PL" as const, fixture: noBtts });
  expect(tiles.some((t) => t.market === "btts")).toBe(false);
  // moneyline + total_goals still present
  expect(tiles).toHaveLength(2);
});

/** PL: omit total_goals tile when predicted_total_goals is null. */
it("PL: omit total_goals tile when predicted_total_goals is null", () => {
  const noTotal = {
    ...plBase(),
    predicted_total_goals: null,
  } as unknown as FixtureSummary;
  const { tiles } = panelFacts({ kind: "PL" as const, fixture: noTotal });
  expect(tiles.some((t) => t.market === "total_goals")).toBe(false);
  // result + btts still present
  expect(tiles).toHaveLength(2);
});

/** ---- SPORTS FIXTURES ---- */

/** Base Sports fixture + prediction. */
const spBase = (): { game: { home_team: string; away_team: string; spread_line: number; total_line: number }; prediction: { home_win_prob: number; away_win_prob: number; predicted_margin: number; predicted_total: number } } => ({
  game: {
    home_team: "KC",
    away_team: "BAL",
    spread_line: -2.5,
    total_line: 44.5,
  },
  prediction: {
    home_win_prob: 0.38,
    away_win_prob: 0.62,
    predicted_margin: -3.4,
    predicted_total: 45.2,
  },
} as unknown as { game: any; prediction: any });

/** Sports: two moneyline segments + leading-tile + spread + total tile. */
it("Sports: two moneyline segments + leading-tile + spread + total tile", () => {
  const { tiles, segments } = panelFacts({
    kind: "SP" as const,
    game: spBase().game,
    prediction: spBase().prediction,
  });
  expect(segments.map((s) => `${s.label} ${s.prob}`)).toEqual(["KC 0.38", "BAL 0.62"]);
  expect(tiles.map((t) => `${t.market}:${t.value}`)).toEqual(["moneyline:62%", "spread:KC +2.5", "total:45.2"]);
  expect(tiles[0].sub).toBe("win · BAL");
  expect(tiles[1].sub).toBe("model +3.4");
  expect(tiles[2].sub).toBe("total pts · line 44.5");
});

/** Sports: flip leading side when probs flip. */
it("Sports: flip leading side when probs flip", () => {
  const { tiles } = panelFacts({
    kind: "SP" as const,
    game: spBase().game,
    prediction: { ...spBase().prediction, home_win_prob: 0.62, away_win_prob: 0.38 },
  });
  expect(tiles[0].sub).toBe("win · KC");
});

/** Sports: no prediction → empty tiles/segments. */
it("Sports: no prediction returns empty", () => {
  const { tiles, segments } = panelFacts({
    kind: "SP" as const,
    game: spBase().game,
    prediction: null as unknown,
  });
  expect(tiles).toEqual([]);
  expect(segments).toEqual([]);
});

/** Sports: omit spread/total when data absent, no empty tile rendered. */
it("Sports: omit spread/total when data absent, no empty tile rendered", () => {
  const { tiles } = panelFacts({
    kind: "SP" as const,
    game: { ...spBase().game, spread_line: null, total_line: null },
    prediction: { ...spBase().prediction, predicted_margin: null, predicted_total: null },
  });
  expect(tiles).toHaveLength(0);
  // moneyline segments still render if probs present
  expect(panelFacts({ kind: "SP" as const, game: spBase().game, prediction: spBase().prediction }).segments).toHaveLength(2);
});

/** Sports: moneyline tile sub "win · <lead team>" when home prob >= away. */
it("Sports: moneyline tile sub wins · home team when home prob >= away", () => {
  const { tiles } = panelFacts({
    kind: "SP" as const,
    game: spBase().game,
    prediction: spBase().prediction,
  });
  expect(tiles[0].sub).toBe("win · BAL");
});

/** Sports: moneyline tile sub wins · away team when away prob > home. */
it("Sports: moneyline tile sub wins · away team when away prob > home", () => {
  const { tiles } = panelFacts({
    kind: "SP" as const,
    game: spBase().game,
    prediction: { ...spBase().prediction, home_win_prob: 0.38, away_win_prob: 0.62 },
  });
  expect(tiles[0].sub).toBe("win · KC");
});

/** Honour: no direction marker / market-disagrees / derived percentage in output. */
it("no direction marker / market-disagrees / derived percentage in output", () => {
  const { tiles, segments } = panelFacts({
    kind: "PL" as const,
    fixture: plBase(),
  });
  const allOutput = [...segments.map((s) => s.label), ...tiles.map((t) => t.label)].join(" ");
  expect(allOutput).not.toContain("home team");
  expect(allOutput).not.toContain("market disagrees");
  expect(allOutput).not.toContain("derived percentage");
});

/** Honour: adapter omits market-line tile when sport has no line market. */
it("adapter omits market-line tile when sport has no line market", () => {
  const { tiles } = panelFacts({
    kind: "PL" as const,
    fixture: plBase(),
  });
  // PL has result tile, not market_line
  expect(tiles.some((t) => t.market === "market_line")).toBe(false);
});

/** Honour: Sports spread tile names home team, sub carries discrepancy. */
it("Sports: spread tile names home team, sub carries discrepancy", () => {
  const { tiles } = panelFacts({
    kind: "SP" as const,
    game: spBase().game,
    prediction: spBase().prediction,
  });
  expect(tiles[1].sub).toBe("model +3.4"); // discrepancy = |(-3.4) - (-2.5)| = 0.9 → "model +3.4" after rounding
});
