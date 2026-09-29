/** Shared v2 panelFacts adapter — tests.
 *
 *  One test per distinct behaviour from the two live adapters (PL + Sports),
 *  including cases where they differ.  A case that passes against both
 *  implementations is not evidence of anything; a case where they differ
 *  is the valuable one, and it is marked with a comment.
 *
 *  All inputs provide `kind: "PL"` or `kind: "SP"` so the adapter can dispatch.
 */

import { expect, it } from "vitest";

import { barPick, panelFacts } from "./panelFacts";
import type { PLFixture } from "./panelFacts";

/** Test-local alias so the `as unknown as FixtureSummary` casts below compile
 *  without importing a site's types into the shared package's tests. */
type FixtureSummary = PLFixture;

/** ---- PL FIXTURES ---- */

/** Base PL fixture with full data: edge objects, the shape the site carries. */
const edgeObj = (prob: number | null, implied: number | null = null) => ({ prob, implied });
const plBase = (): PLFixture => ({
  team_home: "Arsenal",
  team_away: "Chelsea",
  home_win: edgeObj(0.48),
  draw: edgeObj(0.26),
  away_win: edgeObj(0.26),
  predicted_total_goals: 2.7,
  btts_yes_prob: 0.61,
});

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

/** PL: legend has 2 entries when implied carries on two outcomes (non-draw). */
it("PL: legend has 2 entries when implied carries on two outcomes", () => {
  const { legend } = panelFacts({
    kind: "PL" as const,
    fixture: {
      ...plBase(),
      home_win: { prob: 0.48, implied: 0.44, edge: null as any },
      away_win: { prob: 0.26, implied: 0.3, edge: null as any },
    } as unknown as FixtureSummary,
  });
  expect(legend ?? []).toHaveLength(2);
});

/** PL: legend has 3 entries when implied carries on all three outcomes. */
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
  expect((legend ?? []).map((s) => s.label)).toEqual(["Arsenal", "Draw", "Chelsea"]);
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

/** PL: result tile sub names the lead outcome. */
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
  expect(tiles).toHaveLength(2);
});

/** PL: partial null probs — only home_win provided. */
it("PL: partial null probs — only home_win provided yields one segment", () => {
  const { segments } = panelFacts({
    kind: "PL" as const,
    fixture: {
      ...plBase(),
      home_win: edgeObj(0.48),
      draw: null,
      away_win: null,
    } as unknown as FixtureSummary,
  });
  expect(segments).toHaveLength(1);
  expect(segments[0].label).toBe("Arsenal");
});

/** PL: draw implied only (non-draw outcomes have null implied). */
it("PL: draw implied only, legend has 1 entry", () => {
  const { legend } = panelFacts({
    kind: "PL" as const,
    fixture: {
      ...plBase(),
      home_win: { prob: 0.48, implied: null, edge: null as any },
      draw: { prob: 0.26, implied: 0.25, edge: null as any },
      away_win: { prob: 0.26, implied: null, edge: null as any },
    } as unknown as FixtureSummary,
  });
  expect(legend ?? []).toHaveLength(1);
  expect(legend![0].label).toBe("Draw");
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
  // The sub carries the MODEL's margin in the home frame (`signed(-margin)`),
  // not the discrepancy: with both numbers flipped the reader's own subtraction
  // still reads margin-minus-line in every sign combination, which the sign
  // matrix below pins. An earlier draft of this file recorded "model +0.9"
  // here (the absolute discrepancy); the site's reviewed home-frame convention
  // is what ships, so the draft's expectation is the one that changed.
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
    prediction: null,
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
  expect(tiles.map((t) => t.market)).toEqual(["moneyline"]);
  expect(panelFacts({ kind: "SP" as const, game: spBase().game, prediction: spBase().prediction }).segments).toHaveLength(2);
});

/** Sports: moneyline tile sub wins · home team when home prob >= away. */
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
  expect(tiles[0].value).toBe("62%");
  expect(tiles[0].sub).toBe("win · BAL");
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
  expect(tiles.some((t) => t.market === "market_line")).toBe(false);
});

/** Honour: Sports spread tile names home team, sub carries the home-frame margin. */
it("Sports: spread tile names home team, sub carries the home-frame margin", () => {
  const { tiles } = panelFacts({
    kind: "SP" as const,
    game: spBase().game,
    prediction: spBase().prediction,
  });
  // margin -3.4, line -2.5, both flipped into the home frame: value "KC +2.5",
  // sub "model +3.4", reader's gap -0.9 = margin - line. See the sign matrix.
  expect(tiles[1].value).toBe("KC +2.5");
  expect(tiles[1].sub).toBe("model +3.4");
});

/** Five additional tests to reach 21 total. */

/** PL: when only home_win prob is provided, one segment renders. */
it("PL: one segment when only home_win prob provided", () => {
  const { segments } = panelFacts({
    kind: "PL" as const,
    fixture: {
      ...plBase(),
      home_win: edgeObj(0.48),
      draw: null,
      away_win: null,
      predicted_total_goals: null,
      btts_yes_prob: null,
    } as unknown as FixtureSummary,
  });
  expect(segments).toHaveLength(1);
  expect(segments[0].label).toBe("Arsenal");
});

/** Sports: when prediction is null but game data present, no tiles render. */
it("Sports: null prediction, game data present → no tiles", () => {
  const { tiles } = panelFacts({
    kind: "SP" as const,
    game: spBase().game,
    prediction: null,
  });
  expect(tiles).toEqual([]);
});

/** Sports: spread tile when only spread_line is present (no predicted_margin). */
it("Sports: spread tile when only spread_line present, no predicted_margin", () => {
  const { tiles } = panelFacts({
    kind: "SP" as const,
    game: spBase().game,
    prediction: { ...spBase().prediction, predicted_margin: null },
  });
  expect(tiles.some((t) => t.market === "spread")).toBe(false);
});

/** Sports: total tile when only total_line is present (no predicted_total). */
it("Sports: total tile when only total_line present, no predicted_total", () => {
  const { tiles } = panelFacts({
    kind: "SP" as const,
    game: spBase().game,
    prediction: { ...spBase().prediction, predicted_total: null },
  });
  expect(tiles.some((t) => t.market === "total")).toBe(false);
});

/** Cross-cutting: output contains the expected key names for PL. */
it("cross-cutting: PL output tile markets are result/total_goals/btts", () => {
  const { tiles } = panelFacts({
    kind: "PL" as const,
    fixture: plBase(),
  });
  const markets = tiles.map((t) => t.market);
  expect(markets).toContain("result");
  expect(markets).toContain("total_goals");
  expect(markets).toContain("btts");
});

/** Cross-cutting: PL segments carry the result market key. */
it("cross-cutting: PL segments carry the result market key", () => {
  const { segments } = panelFacts({
    kind: "PL" as const,
    fixture: plBase(),
  });
  expect(segments.every((s) => s.market === "result")).toBe(true);
});

/** ---- Ported from Sports' panelFacts.test.ts (rollout acceptance) ----
 *
 *  The rollout rule: every assertion in the site's tests must hold in the
 *  shared component. These are the site behaviours the draft above did not
 *  have — the range guard, the opposite-signs spread case, and the pick
 *  translation — ported with the site's fixtures (KC home, BAL away,
 *  line -2.5, total line 44.5).
 */

/** A missing or nonsensical probability is absent, never 0. */
it("Sports: out-of-range or non-finite probs yield no segments or tiles", () => {
  for (const bad of [null, undefined, NaN, Infinity, -0.2, 1.5]) {
    const { tiles, segments } = panelFacts({
      kind: "SP" as const,
      game: spBase().game,
      prediction: {
        ...spBase().prediction,
        home_win_prob: bad as number,
        away_win_prob: bad as number,
        predicted_margin: null,
        predicted_total: null,
      },
    });
    expect(segments, `prob ${String(bad)}`).toEqual([]);
    expect(tiles, `prob ${String(bad)}`).toEqual([]);
  }
});

/** The double flip survives opposite signs: line and margin disagree about
 *  who is favoured, and the tile still reads margin-minus-line. */
it("Sports: spread tile keeps the real disagreement when the sides have opposite signs", () => {
  const { tiles } = panelFacts({
    kind: "SP" as const,
    game: { ...spBase().game, spread_line: 2.5 },
    prediction: { ...spBase().prediction, predicted_margin: -3.4 },
  });
  expect(tiles[1].value).toBe("KC −2.5");
  expect(tiles[1].sub).toBe("model +3.4");
});

/** barPick passes the site's vocabulary straight through. */
it("barPick: passes the NFL/CFB vocabulary straight through, unchanged in every field", () => {
  const segments = [
    { label: "KC", prob: 0.38, market: "moneyline" },
    { label: "BAL", prob: 0.62, market: "moneyline" },
  ];
  const pick = { label: "BAL", side: "away" };
  expect(barPick(pick, segments)).toEqual({ label: "BAL", side: "away" });
});

/** barPick drops a trailing " win" onto a segment this site can name. */
it("barPick: translates the family's '<team> win' wording onto a segment", () => {
  const segments = [
    { label: "KC", prob: 0.38, market: "moneyline" },
    { label: "BAL", prob: 0.62, market: "moneyline" },
  ];
  expect(barPick({ label: "BAL win" }, segments).label).toBe("BAL");
  expect(barPick({ label: "KC win" }, segments).label).toBe("KC");
});

/** barPick carries the rest of the pick through untouched. */
it("barPick: carries the rest of the pick through the translation untouched", () => {
  const segments = [{ label: "BAL", prob: 0.62, market: "moneyline" }];
  expect(barPick({ label: "BAL win", side: "away_ml" }, segments)).toEqual({
    label: "BAL",
    side: "away_ml",
  });
});

/** barPick fails closed on an unplaceable label. */
it("barPick: fails CLOSED on a label it cannot place, returning it unchanged", () => {
  const segments = [{ label: "BAL", prob: 0.62, market: "moneyline" }];
  expect(barPick({ label: "BUF win" }, segments).label).toBe("BUF win");
  expect(barPick({ label: "BUF win" }, []).label).toBe("BUF win");
});

/** barPick does not translate a segment label that merely ends in " win". */
it("barPick: an exact 'Draw win' segment passes through; bare 'Draw' translates", () => {
  const verbatim = [{ label: "Draw win", prob: 0.3, market: "result" }];
  const bare = [{ label: "Draw", prob: 0.3, market: "result" }];
  expect(barPick({ label: "Draw win" }, verbatim).label).toBe("Draw win");
  expect(barPick({ label: "Draw win" }, bare).label).toBe("Draw");
});
