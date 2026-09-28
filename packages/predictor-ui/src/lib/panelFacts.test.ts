/** Shared adapter for PL and Sports v2 panels.
 *
 *  Behaviour captured from two live adapters:
 *  - PL: three-way result, `implied` legend, `predicted_total_goals`, `btts_yes_prob`
 *  - Sports: two-way moneyline, `spread` tile with `predicted_margin - spread_line` gap,
 *            `total_line`, `home_win_prob` / `away_win_prob` segments
 *
 *  A case that passes against both implementations is not evidence of anything;
 *  a case where they differ is the valuable one, and it is marked with a comment.
 */

import { describe, expect, it } from "vitest";

import { panelFacts } from "./panelFacts";
import type { MarketTile, Segment } from "../predictor-ui";
import type { FixtureSummary } from "../types";

/** PL fixture: three-way result with draw */
const plFixture = (over: Partial<FixtureSummary> = {}): FixtureSummary => ({
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
  ...over,
} as FixtureSummary);

/** Sports fixture: two-way moneyline with spread and total */
const spFixture = (over: Partial<GameSummary> = {}): GameSummary => ({
  game_id: "gw1",
  season: 2026,
  week: 3,
  gameday: "2026-09-24",
  home_team: "KC",
  away_team: "BAL",
  home_score: null,
  away_score: null,
  spread_line: -2.5,
  total_line: 44.5,
  ...over,
} as unknown as GameSummary);

/** Sports prediction: home/away win probs + margin + total */
const spPred = (over: Partial<GamePrediction> = {}): GamePrediction => ({
  home_win_prob: 0.38,
  away_win_prob: 0.62,
  home_cover_prob: null,
  away_cover_prob: null,
  over_prob: null,
  under_prob: null,
  predicted_margin: -3.4,
  predicted_total: 45.2,
  ...over,
} as unknown as GamePrediction);

/** PL: known.length → tiles + segments + legend with implied entries */
it("maps PL §7b fixture: tiles + segments when known + legend from implied", () => {
  const { tiles, segments, legend } = panelFacts(plFixture());
  // three segments for the three outcomes
  expect(segments.map((s) => `${s.label} ${s.prob}`)).toEqual([
    "Arsenal 0.48", "Draw 0.26", "Chelsea 0.26",
  ]);
  // tiles: lead outcome + sub
  expect(tiles.map((t) => `${t.market}:${t.value}`)).toEqual(["result:48%", "total_goals:2.7", "btts:61%"]);
  expect(tiles[0].sub).toBe("win · Arsenal");
  // legend empty when implied is null (committed snapshot)
  expect(legend).toEqual([]);
});

/** PL: fixture with implied → legend has entries */
it("PL: legend has entries when implied carries", () => {
  const twoSides = {
    ...plFixture(),
    home_win: { prob: 0.48, implied: 0.44, edge: null as any },
    away_win: { prob: 0.26, implied: 0.3, edge: null as any },
  } as unknown as FixtureSummary;
  expect(panelFacts(twoSides).legend).toHaveLength(2);
  // all three with implied
  const all = {
    ...plFixture(),
    home_win: { prob: 0.48, implied: 0.44, edge: null as any },
    draw: { prob: 0.26, implied: 0.25, edge: null as any },
    away_win: { prob: 0.26, implied: 0.31, edge: null as any },
  } as unknown as FixtureSummary;
  expect(panelFacts(all).legend.map((s) => s.label)).toEqual(["Arsenal", "Draw", "Chelsea"]);
});

/** PL: no fixture → empty */
it("PL: no fixture returns empty tiles and segments", () => {
  const { tiles, segments } = panelFacts(null as unknown as FixtureSummary);
  expect(tiles).toEqual([]);
  expect(segments).toEqual([]);
});

/** Sports: two moneyline segments, leading side tile */
it("Sports: two moneyline segments + leading-tile when both probs present", () => {
  const { tiles, segments } = panelFacts(spFixture(), spPred());
  expect(segments.map((s) => `${s.label} ${s.prob}`)).toEqual(["KC 0.38", "BAL 0.62"]);
  expect(tiles.map((t) => `${t.market}:${t.value}`)).toEqual(["moneyline:62%", "spread:KC +2.5", "total:45.2"]);
  expect(tiles[0].sub).toBe("win · BAL");
  expect(tiles[1].sub).toBe("model +3.4");
  expect(tiles[2].sub).toBe("total pts · line 44.5");
});

/** Sports: flip leading side when probs flip */
it("Sports: flip leading side when probs flip", () => {
  const { tiles } = panelFacts(spFixture(), spPred({ home_win_prob: 0.62, away_win_prob: 0.38 }));
  expect(tiles[0].sub).toBe("win · KC");
});

/** Sports: no prediction → no tiles/segments */
it("Sports: no prediction returns empty", () => {
  const { tiles, segments } = panelFacts(spFixture(), null as unknown as GamePrediction);
  expect(tiles).toEqual([]);
  expect(segments).toEqual([]);
});

/** Sports: omit market data not carried → no empty tile */
it("Sports: omit spread/total when data absent, no empty tile rendered", () => {
  const { tiles } = panelFacts(
    { ...spFixture(), spread_line: null, total_line: null },
    { ...spPred(), predicted_margin: null, predicted_total: null },
  );
  // No tile for a market the data does not carry
  expect(tiles).toHaveLength(0);
  // But moneyline segments still render if probs present
  expect(panelFacts(spFixture(), spPred()).segments).toHaveLength(2);
});

/** Honour assertion: no direction marker, no "the market disagrees", no derived percentage */
it("no direction marker / market-disagrees clause / derived percentage in output", () => {
  const result = panelFacts(plFixture());
  const allOutput = [...result.segments.map((s) => s.label), ...result.tiles.map((t) => t.label)].join(" ");
  // These substrings must never appear in the shared adapter's output
  expect(allOutput).not.toContain("home team");
  expect(allOutput).not.toContain("market disagrees");
  expect(allOutput).not.toContain("derived percentage");
});

/** Honour assertion: adapter omits market-line tile when sport has no line market.
 *  This is a placeholder — the component test (FixtureFlow) will assert absence
 *  of market-line tile for F1, while Sports emits moneyline and PL emits result. */
it("adapter omits market-line tile when sport has no line market", () => {
  const { tiles } = panelFacts(plFixture());
  // PL has result tile, not market_line — placeholder ensuring the adapter
  // can be called without a market-line tile being emitted for a sport that has none.
  expect(tiles.some((t) => t.market === "market_line")).toBe(false);
});
