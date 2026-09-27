import { test } from "node:test";
import assert from "node:assert/strict";
import { selectF1, selectPL, selectFootball, selectNBA, pct, driverName } from "../teasers.js";

// --- shared formatting ---

test("pct renders a whole percentage and never NaN", () => {
  assert.equal(pct(0.4812), "48%");
  assert.equal(pct(1), "100%");
  assert.equal(pct(null), "—");
  assert.equal(pct(undefined), "—");
  assert.equal(pct(NaN), "—");
  assert.equal(pct(0), "0%");
});

test("driverName title-cases the id exactly as the F1 site does", () => {
  assert.equal(driverName("russell"), "Russell");
  assert.equal(driverName("max_verstappen"), "Max Verstappen");
  // A real name from the API wins over anything derived.
  assert.equal(driverName("russell", "George Russell"), "George Russell");
  assert.equal(driverName("russell", null), "Russell");
});

// --- F1: top three by p_win ---

const F1_RACES = [
  { season: 2026, round: 3, race_name: "Australian Grand Prix", race_datetime: "2026-03-08T05:00:00Z", completed: true },
  { season: 2026, round: 4, race_name: "Chinese Grand Prix", race_datetime: "2026-03-15T05:00:00Z", completed: false },
];

test("F1 picks the next race, not the last finished one", () => {
  const out = selectF1(F1_RACES, {
    3: { source: "tracked", predictions: [{ driver_id: "a", p_win: 0.9 }] },
    4: { source: "tracked", predictions: [{ driver_id: "b", p_win: 0.2 }] },
  });
  assert.equal(out.label, "Chinese Grand Prix");
  assert.deepEqual(out.rows.map((r) => r.name), ["B"]);
});

test("F1 takes the top three by win probability", () => {
  const out = selectF1(F1_RACES, {
    4: {
      source: "tracked",
      predictions: [
        { driver_id: "russell", p_win: 0.15 },
        { driver_id: "norris", p_win: 0.40 },
        { driver_id: "verstappen", p_win: 0.30 },
        { driver_id: "hamilton", p_win: 0.09 },
        { driver_id: "leclerc", p_win: 0.06 },
      ],
    },
  });
  assert.deepEqual(out.rows.map((r) => r.name), ["Norris", "Verstappen", "Russell"]);
  assert.equal(out.rows.length, 3);
});

test("F1 refuses to present a rebuilt or backtest pick as a pre-race call", () => {
  const out = selectF1(F1_RACES, { 4: { source: "rebuilt", predictions: [{ driver_id: "russell", p_win: 0.5 }] } });
  assert.equal(out.rows.length, 0);
  assert.match(out.empty, /after the session|race/i);
});

test("F1 hides a pick from an unrecognised source rather than showing it", () => {
  // isPreEvent is a whitelist on purpose: an unknown source might be
  // post-event, and showing it as a pre-race call would be a lie, while
  // hiding a genuinely pre-event source merely omits a row.
  const out = selectF1(F1_RACES, { 4: { source: "model", predictions: [{ driver_id: "russell", p_win: 0.5 }] } });
  assert.equal(out.rows.length, 0);
  assert.ok(out.empty, "an unrecognised source must not render as a call");
});

test("F1 with no upcoming race says so rather than showing the last one", () => {
  const out = selectF1([F1_RACES[0]], { 3: { source: "tracked", predictions: [{ driver_id: "a", p_win: 0.5 }] } });
  assert.equal(out.rows.length, 0);
  assert.match(out.empty, /season/i);
});

// --- PL: strongest pick ---

test("PL picks the fixture the model is most sure about", () => {
  const out = selectPL({
    current_gameweek: 9,
    fixtures_by_gameweek: {
      9: {
        gameweek: 9,
        fixtures: [
          { event_id: "1", team_home: "A", team_away: "B", predicted_home_win: 0.44, predicted_draw: 0.25, predicted_away_win: 0.31, predicted_scoreline: "1-1", has_live_odds: false, value_bet_flags: [] },
          { event_id: "2", team_home: "C", team_away: "D", predicted_home_win: 0.86, predicted_draw: 0.08, predicted_away_win: 0.06, predicted_scoreline: "3-0", has_live_odds: false, value_bet_flags: [] },
        ],
      },
    },
  });
  assert.equal(out.rows[0].name, "C v D");
  assert.equal(out.rows[0].value, "86%");
});

test("PL reads a draw as a pick in its own right", () => {
  // A fixture where the draw is the model's call must not be skipped for
  // having no favoured side. PRODUCT.md calls this a toss-up.
  const out = selectPL({
    current_gameweek: 9,
    fixtures_by_gameweek: { 9: { gameweek: 9, fixtures: [
      { event_id: "1", team_home: "A", team_away: "B", predicted_home_win: 0.36, predicted_draw: 0.40, predicted_away_win: 0.24, predicted_scoreline: "1-1", has_live_odds: false, value_bet_flags: [] },
    ] } },
  });
  assert.equal(out.rows[0].value, "40%");
  assert.match(out.rows[0].pick, /draw/i);
});

test("PL shows an edge only when a real line exists", () => {
  const base = { current_gameweek: 9, fixtures_by_gameweek: { 9: { gameweek: 9, fixtures: [
    { event_id: "1", team_home: "A", team_away: "B", predicted_home_win: 0.86, predicted_draw: 0.08, predicted_away_win: 0.06, predicted_scoreline: "3-0", has_live_odds: false, value_bet_flags: [] },
  ] } } };
  assert.equal(selectPL(base).rows[0].edge, undefined);
  const withOdds = { current_gameweek: 9, fixtures_by_gameweek: { 9: { gameweek: 9, fixtures: [
    { ...base.fixtures_by_gameweek[9].fixtures[0], has_live_odds: true, value_bet_flags: ["home_win"] },
  ] } } };
  assert.ok(selectPL(withOdds).rows[0].edge, "a real line must produce an edge");
});

// --- NFL / CFB: closest to a coin flip ---

test("the football card picks the game closest to a coin flip", () => {
  const out = selectFootball(
    [
      { game_id: "g1", home_team: "AAA", away_team: "BBB", gameday: "2026-11-05T00:00:00", spread_line: null },
      { game_id: "g2", home_team: "CCC", away_team: "DDD", gameday: "2026-11-05T00:00:00", spread_line: -2.5 },
      { game_id: "g3", home_team: "EEE", away_team: "FFF", gameday: "2026-11-05T00:00:00", spread_line: null },
    ],
    {
      g1: { home_win_prob: 0.60, away_win_prob: 0.40 },
      g2: { home_win_prob: 0.62, away_win_prob: 0.38 },
      g3: { home_win_prob: 0.51, away_win_prob: 0.49 },
    },
  );
  assert.equal(out.rows[0].name, "EEE v FFF", "closest to 50% wins, not the first or the biggest favourite");
  assert.equal(out.rows[0].value, "51%");
});

test("the football card is the one that carries the line", () => {
  // Only the closest game is shown, so a line on any other game is irrelevant.
  const out = selectFootball(
    [
      { game_id: "g1", home_team: "AAA", away_team: "BBB", gameday: "2026-11-05T00:00:00", spread_line: -7 },
      { game_id: "g2", home_team: "CCC", away_team: "DDD", gameday: "2026-11-05T00:00:00", spread_line: null },
    ],
    { g1: { home_win_prob: 0.80, away_win_prob: 0.20 }, g2: { home_win_prob: 0.52, away_win_prob: 0.48 } },
  );
  assert.equal(out.rows[0].name, "CCC v DDD");
  assert.equal(out.rows[0].edge, undefined, "the shown game has no line, so no edge is claimed");
});

test("the football card ignores finished games", () => {
  const out = selectFootball(
    [
      { game_id: "g1", home_team: "AAA", away_team: "BBB", gameday: "2026-11-01T00:00:00", home_score: 24, away_score: 10, spread_line: null },
      { game_id: "g2", home_team: "CCC", away_team: "DDD", gameday: "2026-11-08T00:00:00", home_score: null, away_score: null, spread_line: null },
    ],
    { g1: { home_win_prob: 0.50, away_win_prob: 0.50 }, g2: { home_win_prob: 0.70, away_win_prob: 0.30 } },
  );
  assert.equal(out.rows[0].name, "CCC v DDD");
});

test("the football card says so when the week has no games left", () => {
  const out = selectFootball([{ game_id: "g1", home_team: "A", away_team: "B", gameday: "2026-11-01T00:00:00", home_score: 1, away_score: 0 }], {});
  assert.equal(out.rows.length, 0);
  assert.ok(out.empty);
});

// --- NBA: closest to a coin flip ---

test("NBA picks the closest game among those with a prediction", () => {
  const out = selectNBA([
    { game_id: "1", home_team: "NYK", away_team: "BOS", completed: false, prediction: { home_win_prob: 0.55 } },
    { game_id: "2", home_team: "LAL", away_team: "GSW", completed: false, prediction: { home_win_prob: 0.50 } },
    { game_id: "3", home_team: "MIA", away_team: "DAL", completed: false, prediction: null },
    { game_id: "4", home_team: "BOS", away_team: "NYK", completed: true, prediction: { home_win_prob: 0.50 }, home_pts: 110, away_pts: 99 },
  ]);
  assert.equal(out.rows[0].name, "LAL v GSW");
  assert.equal(out.rows[0].value, "50%");
});

// --- render contract (Task 7, asserted textually: no jsdom in this repo) ---

import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../teasers.js", import.meta.url), "utf8");

test("every teaser slot ends up with aria-busy removed, on every path", () => {
  // aria-busy is what tells a screen reader the region is still settling. If
  // any return path leaves it set, the region is announced as loading
  // forever -- the exact failure the Phase 1 audit found on the sport sites.
  assert.match(src, /aria-busy/, "aria-busy is never cleared");
  assert.match(src, /setAttribute\(\s*["']aria-busy["']\s*,\s*["']false["']/);
});

test("one failed sport never touches another sport's slot", () => {
  assert.match(src, /catch/, "no catch: a rejected fetch would leave the board half-filled");
  // Each sport is fetched in its own promise, not in one Promise.all, so a
  // single rejection cannot short-circuit the rest.
  assert.doesNotMatch(src, /await Promise\.all/, "Promise.all short-circuits on the first rejection");
});

test("the F1 teaser renders its source as its timing signal", () => {
  // Measured 2026-09-27: no endpoint the hub calls returns `generated_at` --
  // it exists only at the top level of each public_snapshot.json, which no
  // hub route serves -- so no teaser can carry a snapshot date today. That
  // absence is a documented known limitation (see the note on `freshness` in
  // teasers.js), not an oversight. The F1 teaser's `Source:` line stays as
  // the one real timing signal available: tracked versus live versus rebuilt
  // is exactly the distinction that matters on that sport.
  assert.match(src, /Source: \$\{prediction\.source\}/, "F1 source line removed: the board loses its only timing signal");
  assert.match(src, /no endpoint.*generated_at/is, "the missing-timestamp limitation must stay documented, not silent");
});
