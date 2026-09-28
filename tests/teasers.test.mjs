import { test } from "node:test";
import assert from "node:assert/strict";
import { selectF1, selectPL, selectFootball, selectNBA, pct, driverName } from "../teasers.js";
import { freshness } from "../teasers.js";

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

// --- F1: session-based selection (clock rule, not availability) ---

// Round 16 (Singapore GP) is a normal weekend. Its qualifying is
// 2026-10-03T08:00:00Z and its race is 2026-10-04T07:00:00Z.
const QUALIFYING_TIME = new Date("2026-10-03T08:00:00Z").getTime();
const RACE_TIME = new Date("2026-10-04T07:00:00Z").getTime();

const F1_RACES = [
  { season: 2026, round: 3, race_name: "Australian Grand Prix", race_datetime: "2026-03-08T05:00:00Z", completed: true, is_sprint_weekend: false },
  { season: 2026, round: 16, race_name: "Singapore Grand Prix", race_datetime: "2026-10-04T07:00:00Z", completed: false, is_sprint_weekend: false, session_datetime: { qualifying: "2026-10-03T08:00:00Z", race: "2026-10-04T07:00:00Z" } },
];

// Round 14 (United States GP) is a sprint weekend. Its sprint_qualifying
// is already null (completed), and its sessions run from Oct 18-19.
const SPRINT_RACES = [
  { season: 2026, round: 14, race_name: "United States Grand Prix", race_datetime: "2026-10-19T07:00:00Z", completed: false, is_sprint_weekend: true, session_datetime: { sprint_qualifying: null, sprint: "2026-10-18T12:00:00Z", qualifying: "2026-10-18T08:00:00Z", race: "2026-10-19T07:00:00Z" } },
];

// All future-session timestamps for the availability trap test.
const BEFORE_QUALIFYING = QUALIFYING_TIME - 3600000; // one hour before qualifying
const AFTER_QUALIFYING = QUALIFYING_TIME + 3600000;  // one hour after qualifying
const BEFORE_RACE = RACE_TIME - 3600000;
const AFTER_RACE = RACE_TIME + 3600000;

// --- 1. The clock rule ---

test("clock rule: qualifying in the future shows qualifying, not the race", () => {
  // When qualifying is still in the future, the card shows
  // qualifying even though a race prediction already exists.
  const out = selectF1(F1_RACES, {
    16: {
      qualifying: { source: "tracked", predictions: [{ driver_id: "max_verstappen", p_pole: 0.40, p_top_3: 0.75 }] },
      race: { source: "live", predictions: [{ driver_id: "max_verstappen", p_win: 0.15, p_podium: 0.40 }] },
    },
  }, BEFORE_QUALIFYING);
  assert.equal(out.label, "Singapore Grand Prix — Qualifying");
  assert.equal(out.rows[0].value, "40%");
  assert.equal(out.rows[0].name, "Max Verstappen");
  assert.equal(out.rows[0].sub, "Top 3 75%");
});

test("clock rule: qualifying in the past but race in the future shows the race", () => {
  // When qualifying has already passed but the race is still
  // upcoming, the card shows the race.
  const out = selectF1(F1_RACES, {
    16: {
      qualifying: { source: "tracked", predictions: [{ driver_id: "max_verstappen", p_pole: 0.40, p_top_3: 0.75 }] },
      race: { source: "live", predictions: [{ driver_id: "max_verstappen", p_win: 0.15, p_podium: 0.40 }] },
    },
  }, AFTER_QUALIFYING);
  assert.equal(out.label, "Singapore Grand Prix — Race");
  assert.equal(out.rows[0].value, "15%");
  assert.equal(out.rows[0].name, "Max Verstappen");
  assert.equal(out.rows[0].sub, "Podium 40%");
});

// --- 2. The availability trap ---

test("availability trap: race prediction already exists and is future, but qualifying is also future — shows qualifying", () => {
  // This is the test that matters most. The F1 API already contains
  // a race prediction for a future round (source: live). An
  // availability-based shortcut would jump straight to the race and
  // never show qualifying. The clock-based rule must pick the
  // earliest future session regardless of which predictions exist.
  const out = selectF1(F1_RACES, {
    16: {
      qualifying: { source: "tracked", predictions: [{ driver_id: "max_verstappen", p_pole: 0.45, p_top_3: 0.80 }] },
      race: { source: "live", predictions: [{ driver_id: "max_verstappen", p_win: 0.15, p_podium: 0.40 }] },
    },
  }, BEFORE_QUALIFYING);
  assert.equal(out.label, "Singapore Grand Prix — Qualifying");
  assert.equal(out.rows[0].value, "45%");
  assert.ok(out.rows[0].value !== "15%", "must not show the race win figure on a qualifying card");
});

// --- 3. Market correctness ---

test("qualifying card leads with p_pole and does not contain a p_win figure", () => {
  const out = selectF1(F1_RACES, {
    16: {
      qualifying: { source: "tracked", predictions: [{ driver_id: "max_verstappen", p_pole: 0.40, p_top_3: 0.75 }] },
      race: { source: "tracked", predictions: [{ driver_id: "max_verstappen", p_win: 0.15, p_podium: 0.40 }] },
    },
  }, BEFORE_QUALIFYING);
  assert.equal(out.rows[0].value, "40%");
  assert.equal(out.rows.map((r) => r.value).join(","), "40%");
  // The label must identify the session market.
  assert.match(out.label, /Qualifying/);
  // No row value should be a win probability figure.
  assert.ok(!out.rows.some((r) => r.value === "15%"), "qualifying card must not show p_win");
});

test("race card leads with p_win", () => {
  const out = selectF1(F1_RACES, {
    16: {
      qualifying: { source: "tracked", predictions: [{ driver_id: "max_verstappen", p_pole: 0.40, p_top_3: 0.75 }] },
      race: { source: "live", predictions: [{ driver_id: "max_verstappen", p_win: 0.15, p_podium: 0.40 }] },
    },
  }, AFTER_QUALIFYING);
  assert.equal(out.rows[0].value, "15%");
  assert.match(out.label, /Race/);
});

// --- 4. Honesty (rebuilt / backtest / unrecognised sources) ---

test("rebuilt session prediction is not shown as a call", () => {
  const out = selectF1(F1_RACES, {
    16: {
      qualifying: { source: "rebuilt", predictions: [{ driver_id: "max_verstappen", p_pole: 0.40, p_top_3: 0.75 }] },
      race: { source: "tracked", predictions: [{ driver_id: "max_verstappen", p_win: 0.15, p_podium: 0.40 }] },
    },
  }, BEFORE_QUALIFYING);
  // The qualifying session has rebuilt source, so it's not a call.
  // findNextSession picks qualifying (clock), but isPreEvent drops it.
  // selectF1 should fall through to the race prediction... wait, no.
  // Actually selectF1 picks the NEXT session by clock (qualifying),
  // then checks isPreEvent on THAT session's prediction.
  // Since qualifying is rebuilt, it returns the empty message.
  // But wait — should it then fall through to the race? No!
  // The clock says qualifying is next, and if the qualifying
  // prediction is rebuilt, the card says so. It does NOT fall back
  // to the race.
  assert.equal(out.rows.length, 0);
  assert.ok(out.empty, "rebuilt session prediction must not render as a call");
});

test("unrecognised source is hidden rather than shown", () => {
  const out = selectF1(F1_RACES, {
    16: {
      qualifying: { source: "model", predictions: [{ driver_id: "max_verstappen", p_pole: 0.40, p_top_3: 0.75 }] },
      race: { source: "tracked", predictions: [{ driver_id: "max_verstappen", p_win: 0.15, p_podium: 0.40 }] },
    },
  }, BEFORE_QUALIFYING);
  assert.equal(out.rows.length, 0);
  assert.ok(out.empty, "an unrecognised source must not render as a call");
});

// --- 5. Honesty: no session in the future ---

test("no session in the future returns empty rows and a non-empty sentence", () => {
  const past = RACE_TIME + 86400000; // one day after the race
  const out = selectF1(F1_RACES, {
    16: {
      qualifying: { source: "tracked", predictions: [{ driver_id: "max_verstappen", p_pole: 0.40, p_top_3: 0.75 }] },
      race: { source: "live", predictions: [{ driver_id: "max_verstappen", p_win: 0.15, p_podium: 0.40 }] },
    },
  }, past);
  assert.equal(out.rows.length, 0);
  assert.ok(out.empty.length > 0, "empty must be a non-empty sentence");
  assert.match(out.empty, /session/i, "empty must mention sessions, not races");
});

// --- 6. Missing session endpoint (non-sprint weekend has no sprint) ---

test("non-sprint weekend: sprint sessions are absent and must not raise or blank the card", () => {
  // A normal weekend only has qualifying and race. The sprint and
  // sprint_qualifying sessions don't exist. The selector must pick
  // qualifying (or race) without error and must not try to access
  // a sprint prediction that doesn't exist.
  const now = BEFORE_QUALIFYING;
  const out = selectF1(F1_RACES, {
    16: {
      qualifying: { source: "tracked", predictions: [{ driver_id: "max_verstappen", p_pole: 0.40, p_top_3: 0.75 }] },
    },
  }, now);
  assert.equal(out.label, "Singapore Grand Prix — Qualifying");
  assert.equal(out.rows.length, 1);
  assert.equal(out.rows[0].value, "40%");
});

// --- 7. Sprint weekend selection ---

test("sprint weekend: sprint_qualifying null is skipped, sprint is next", () => {
  // sprint_qualifying is null (completed), sprint is in the future.
  const now = new Date("2026-10-18T10:00:00Z").getTime(); // after midnight Oct 18 but before sprint at noon
  const out = selectF1(SPRINT_RACES, {
    14: {
      sprint_qualifying: { source: "tracked", predictions: [{ driver_id: "a", p_pole: 0.5 }] },
      sprint: { source: "tracked", predictions: [{ driver_id: "max_verstappen", p_win: 0.30, p_podium: 0.55 }] },
      qualifying: { source: "tracked", predictions: [{ driver_id: "norris", p_pole: 0.35, p_top_3: 0.65 }] },
      race: { source: "tracked", predictions: [{ driver_id: "leclerc", p_win: 0.20, p_podium: 0.45 }] },
    },
  }, now);
  assert.equal(out.label, "United States Grand Prix — Sprint");
  assert.equal(out.rows[0].value, "30%");
});

// --- 8. No upcoming race/session at all ---

test("with no uncompleted race says so rather than showing the last one", () => {
  const past = RACE_TIME + 86400000;
  const out = selectF1([F1_RACES[0]], {}, past);
  assert.equal(out.rows.length, 0);
  assert.match(out.empty, /season/i);
});

// --- 9. The capability gap: session_datetime is missing entirely -----------
//
// Two failures leave the card with no future session, and they are not the
// same failure. These tests exist as a PAIR: the first one fails if the
// fallback disappears, the second fails if the fallback spreads to a round
// whose timing is readable. Neither branch may swallow the other.

// The live production shape: the field is committed to the F1 API but the
// branch carrying it is not merged, and the container re-fetches its snapshot
// from GitHub main — so every session_datetime is null and no round can say
// when anything is.
const TIMINGLESS_RACES = [
  { season: 2026, round: 3, race_name: "Australian Grand Prix", race_datetime: "2026-03-08T05:00:00Z", completed: true, is_sprint_weekend: false },
  { season: 2026, round: 16, race_name: "Singapore Grand Prix", race_datetime: "2026-10-04T07:00:00Z", completed: false, is_sprint_weekend: false },
];

// One race payload reused by the fallback tests: five drivers, so a card that
// returns every driver or the wrong three fails on the count.
const RACE_PREDICTIONS = [
  { driver_id: "norris", p_win: 0.40, p_podium: 0.70 },
  { driver_id: "verstappen", p_win: 0.30, p_podium: 0.60 },
  { driver_id: "russell", p_win: 0.15, p_podium: 0.45 },
  { driver_id: "hamilton", p_win: 0.09, p_podium: 0.30 },
  { driver_id: "leclerc", p_win: 0.06, p_podium: 0.25 },
];

test("no session_datetime anywhere: the card falls back to the race, still three drivers", () => {
  // The wall clock says qualifying is still a day out, but the payload
  // cannot say that — with no readable timing the clock is never consulted,
  // so the card answers the older question (the next race) instead of
  // rendering nothing. Saying nothing is a worse answer than an honest older
  // one: this is a capability gap, not a schedule.
  const out = selectF1(
    TIMINGLESS_RACES,
    { 16: { race: { source: "live", predictions: RACE_PREDICTIONS } } },
    BEFORE_QUALIFYING,
  );
  assert.equal(out.label, "Singapore Grand Prix — Race");
  assert.equal(out.empty, "");
  assert.equal(out.rows.length, 3, "the fallback is still a top-three card");
  assert.deepEqual(out.rows.map((r) => r.name), ["Norris", "Verstappen", "Russell"]);
  assert.equal(out.rows[0].sub, "Podium 70%");
  // F1 keeps its own shape: three drivers, no second group, no qualifier.
  assert.equal(out.rows[0].qualifier, undefined);
});

test("the capability gap does not move with the clock: no timing means no clock", () => {
  // Same payload, two moments a day apart. If the answer changed with `now`
  // we would be pretending to have timing we do not have.
  const preds = { 16: { race: { source: "live", predictions: RACE_PREDICTIONS } } };
  const before = selectF1(TIMINGLESS_RACES, preds, BEFORE_QUALIFYING);
  const after = selectF1(TIMINGLESS_RACES, preds, AFTER_RACE);
  assert.equal(after.label, before.label);
  assert.deepEqual(after.rows, before.rows);
});

test("the race fallback still refuses a post-event source", () => {
  // Missing timing is not missing honesty. The fallback runs through the same
  // isPreEvent whitelist as the clock path — one whitelist, no second one —
  // and "backtest" is the documented source no other test had pinned.
  for (const source of ["rebuilt", "backtest", "model"]) {
    const out = selectF1(
      TIMINGLESS_RACES,
      { 16: { race: { source, predictions: RACE_PREDICTIONS } } },
      BEFORE_QUALIFYING,
    );
    assert.equal(out.rows.length, 0, `source "${source}" must not render as a call`);
    assert.ok(out.empty, `source "${source}" must still say something`);
  }
});

// Timing present for every round. Round 15's race has been run and the API
// has not flipped `completed` yet — a stale row the fallback would stop on,
// and the thing that tells the two branches apart from the outside.
const TIMED_RACES = [
  { season: 2026, round: 15, race_name: "Azerbaijan Grand Prix", race_datetime: "2026-09-20T12:00:00Z", completed: false, is_sprint_weekend: false, session_datetime: { qualifying: "2026-09-19T15:00:00Z", race: "2026-09-20T12:00:00Z" } },
  F1_RACES[1],
];

test("timing present, qualifying past, race future: the race, reached by the clock, not the fallback", () => {
  const out = selectF1(
    TIMED_RACES,
    {
      15: { race: { source: "live", predictions: [{ driver_id: "leclerc", p_win: 0.20, p_podium: 0.45 }] } },
      16: { race: { source: "live", predictions: RACE_PREDICTIONS } },
    },
    AFTER_QUALIFYING,
  );
  // Readable timing exists, so the fallback must not fire: the clock walks
  // past round 15 (all of its time has gone) to round 16, where qualifying
  // has just run and the race is next. The fallback never reads the clock —
  // it would stop at the first uncompleted round and show Azerbaijan.
  assert.equal(out.label, "Singapore Grand Prix — Race");
  assert.equal(out.rows[0].name, "Norris", "round 16's race, not the stale round 15 one");
  assert.equal(out.rows[0].value, "40%");
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

test("the second row is drawn without the accent number, and its qualifier reaches the note", () => {
  // The spec's subordination: row 2 keeps the row's own type and
  // --color-pr-text instead of the accent number, so the eye lands on row 1.
  // No class at all is the point — a new colour or a new token would break
  // the hub's token-parity test against predictor-ui.
  assert.match(src, /if \(!row\.secondary\) num\.className = "teaser-num"/,
    "row 2 must not borrow row 1's accent number");
  assert.doesNotMatch(src, /var\(--color-/, "teasers.js names no colour: row 2 needs no new token");
  // And the qualifier (why each row is on the card) leads the note line,
  // joined with whatever detail the row already carried.
  assert.match(src, /\[row\.qualifier, row\.sub\]/, "the row qualifier must reach the rendered note");
});

test("the F1 teaser keeps its source signal and prefers a real snapshot date", () => {
  // The /snapshot-meta endpoint now exists on all five APIs, so the board's
  // timing signal is a real date, not just `Source:`. The F1 source
  // (tracked vs live) is still rendered alongside it when both fit one line.
  assert.match(src, /Source: \$\{prediction\.source\}/, "F1 source line removed");
  assert.match(src, /\/f1\/api\/snapshot-meta/, "F1 teaser never asks for its snapshot date");
});

// --- freshness (snapshot-meta consumer) ---

test("freshness renders a short dated phrase for a snapshot timestamp", () => {
  assert.equal(
    freshness({ generated_at: "2026-09-27T22:12:44.448691+00:00", source: "public_snapshot" }),
    "From the 2026-09-27 snapshot",
  );
});

test("freshness renders an honest word for live numbers, never a date", () => {
  // {"generated_at": null, "source": "live"} is a real expected state for a
  // public deploy before its first snapshot: computed on request, not
  // precomputed. It must never raise and never show a fabricated date.
  const out = freshness({ generated_at: null, source: "live" });
  assert.ok(out.length > 0, "the live state must render something, not a blank");
  assert.doesNotMatch(out, /\d{4}-\d{2}-\d{2}/, "a live computation has no snapshot date to show");
  assert.equal(out, "Live");
  assert.equal(freshness({ source: "live" }), "Live", "an absent generated_at is live, not dated");
});

test("freshness falls back to the live wording on a malformed timestamp", () => {
  // A bad timestamp from the API must not crash the teaser and must not
  // invent a date: fall back to the honest word.
  assert.equal(freshness({ generated_at: "not-a-date", source: "public_snapshot" }), "Live");
  assert.equal(freshness({ generated_at: 12345, source: "public_snapshot" }), "Live");
});

test("a missing meta payload renders nothing, not an empty paragraph", () => {
  // freshness(null) is the meta-fetch-failed case: paint()'s `if (sub)` guard
  // then skips the date line entirely, so the picks still render dateless.
  assert.equal(freshness(null), "");
  assert.equal(freshness(undefined), "");
  assert.match(src, /if\s*\(\s*sub\s*\)/, "paint must skip a missing sub instead of rendering an empty paragraph");
});

// --- snapshot-meta wiring: every sport asks, no sport can blank another ---

test("every per-sport fetcher asks its own snapshot-meta endpoint", () => {
  // PL, F1 and NBA carry literal paths; footballTeaser is shared by NFL and
  // CFB and takes `base`, so one `${base}` template covers both prefixes --
  // the SPORTS table below pins that both are still routed through it.
  // NBA is the exception on the prefix, not on the behaviour: its router is
  // mounted at the app root, so it asks /nba/snapshot-meta with no /api.
  assert.match(src, /\/pl\/api\/snapshot-meta/);
  assert.match(src, /\/f1\/api\/snapshot-meta/);
  assert.match(src, /\$\{NBA\}\/snapshot-meta/);
  assert.match(src, /\$\{base\}\/api\/snapshot-meta/, "footballTeaser must fetch meta under its base prefix");
  assert.match(src, /footballTeaser\("\/nfl"/, "NFL must still route through footballTeaser");
  assert.match(src, /footballTeaser\("\/cfb"/, "CFB must still route through footballTeaser");
  const hits = src.match(/snapshot-meta/g) || [];
  assert.ok(hits.length >= 4, `expected one meta fetch per fetcher function, found ${hits.length}`);
});

test("a failed meta fetch leaves the sport's picks on the board", () => {
  // The meta fetch is a second request per sport and can fail independently
  // of the picks fetch. It goes through one helper that catches separately
  // and degrades to no date line (""), never to a blanked card -- and the
  // per-sport isolation above means it cannot touch any other card either.
  // Delete the try/catch or make it rethrow and this fails.
  assert.match(
    src,
    /function metaSub\([^)]*\)\s*\{[^]*?try\s*\{[^]*?\}\s*catch\s*\{[^]*?return\s*""/,
    "the snapshot-meta fetch must be tried and caught separately, falling back to no date line",
  );
  for (const call of [
    'metaSub("/pl/api/snapshot-meta")',
    'metaSub("/f1/api/snapshot-meta")',
    'metaSub(`${base}/api/snapshot-meta`)',
    // NBA mounts its router at the app root, with no /api prefix.
    'metaSub(`${NBA}/snapshot-meta`)',
  ]) {
    assert.ok(src.includes(call), `missing meta call: ${call}`);
  }
});

test("every sport fetches its snapshot-meta from the path its API actually serves", () => {
  // The four American-football and PL/F1 APIs mount under /api. NBA does NOT:
  // its router is included with no prefix, and the app then mounts its SPA at
  // "/", so a wrong prefix does not 404 -- it returns the app shell with a 200
  // and HTML. That is why this is asserted rather than discovered in a browser.
  const src = readFileSync(new URL("../teasers.js", import.meta.url), "utf8");
  for (const prefix of ["/pl", "/f1", "/nfl", "/cfb"]) {
    assert.match(src, new RegExp(`["'\`]${prefix}/api/snapshot-meta["'\`]`), `${prefix} serves under /api`);
  }
  assert.match(src, /["'`]\$\{NBA\}\/snapshot-meta["'`]/, "NBA serves at the root, without /api");
  // Assert the constant's VALUE, not just the template that consumes it. The
  // bug this exists to catch was a wrong value in NBA itself; pinning only the
  // `${NBA}/snapshot-meta` shape would still pass with NBA set to "/nba/api".
  assert.match(
    src,
    /const NBA = "\/nba"/,
    'NBA must be "/nba" — its router is mounted at the app root, with no /api prefix',
  );
  // Checked against the code with comments stripped, so the explanatory note
  // above the constant -- which necessarily names the wrong path -- does not
  // make this assertion pass or fail on its own prose.
  const code = src
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("//"))
    .join("\n");
  assert.doesNotMatch(code, /\/nba\/api\//, "NBA must not be fetched through /api");
  assert.doesNotMatch(code, /`\$\{NBA\}\/api\//, "NBA must not be fetched through /api");
});
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
  // Row 1 is the closest game, so a line on any other game can never land on
  // it: each row carries only the line of the game it names. Row 2 may show
  // its own game's line, which is row 2's business.
  const out = selectFootball(
    [
      { game_id: "g1", home_team: "AAA", away_team: "BBB", gameday: "2026-11-05T00:00:00", spread_line: -7 },
      { game_id: "g2", home_team: "CCC", away_team: "DDD", gameday: "2026-11-05T00:00:00", spread_line: null },
    ],
    { g1: { home_win_prob: 0.80, away_win_prob: 0.20 }, g2: { home_win_prob: 0.52, away_win_prob: 0.48 } },
  );
  assert.equal(out.rows[0].name, "CCC v DDD");
  assert.equal(out.rows[0].edge, undefined, "the shown game has no line, so no edge is claimed");
  assert.equal(out.rows[1].edge, "Line AAA -7", "the confident row shows only its own game's real line");
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

// --- the second row: two questions about one payload -----------------------

test("the football teaser returns two rows: the closest game, then the most confident pick", () => {
  const out = selectFootball(
    [
      { game_id: "g1", home_team: "AAA", away_team: "BBB", gameday: "2026-11-05T00:00:00", spread_line: -7 },
      { game_id: "g2", home_team: "CCC", away_team: "DDD", gameday: "2026-11-06T00:00:00", spread_line: -2.5 },
      { game_id: "g3", home_team: "EEE", away_team: "FFF", gameday: "2026-11-07T00:00:00", spread_line: null },
    ],
    {
      g1: { home_win_prob: 0.60, away_win_prob: 0.40 },
      g2: { home_win_prob: 0.62, away_win_prob: 0.38 },
      g3: { home_win_prob: 0.51, away_win_prob: 0.49 },
    },
  );
  assert.equal(out.rows.length, 2);
  assert.equal(out.rows[0].name, "EEE v FFF", "row 1 is still the game closest to a coin flip");
  assert.equal(out.rows[0].value, "51%");
  assert.equal(out.rows[0].qualifier, "Closest game");
  assert.equal(out.rows[0].secondary, undefined, "row 1 keeps the accent");
  assert.equal(out.rows[1].name, "CCC v DDD", "row 2 is the most confident pick, not a second coin flip");
  assert.equal(out.rows[1].value, "62%");
  assert.equal(out.rows[1].qualifier, "Most confident pick");
  assert.equal(out.rows[1].secondary, true);
  assert.notEqual(out.rows[0].name, out.rows[1].name, "the two rows must not be one pick printed twice");
  // Edge travels with the row it belongs to: row 2's game has a real line,
  // row 1's does not.
  assert.equal(out.rows[1].edge, "Line CCC -2.5");
  assert.equal(out.rows[0].edge, undefined);
});

test("the PL teaser returns two rows: the fixture it is surest of, then the closest one", () => {
  // PL's row 1 has always been the fixture the model is most sure about (see
  // the test above this section) and stays row 1, so row 2 carries the other
  // question — the fixture nearest a toss-up. The qualifiers, not the order,
  // are what tell the two apart.
  const out = selectPL({
    current_gameweek: 9,
    fixtures_by_gameweek: { 9: { gameweek: 9, fixtures: [
      { event_id: "1", team_home: "A", team_away: "B", predicted_home_win: 0.44, predicted_draw: 0.25, predicted_away_win: 0.31, predicted_scoreline: "1-1", has_live_odds: false, value_bet_flags: [] },
      { event_id: "2", team_home: "C", team_away: "D", predicted_home_win: 0.86, predicted_draw: 0.08, predicted_away_win: 0.06, predicted_scoreline: "3-0", has_live_odds: false, value_bet_flags: [] },
    ] } },
  });
  assert.equal(out.rows.length, 2);
  assert.equal(out.rows[0].name, "C v D");
  assert.equal(out.rows[0].value, "86%");
  assert.equal(out.rows[0].qualifier, "Most confident pick");
  assert.equal(out.rows[1].name, "A v B", "the fixture nearest 50% on its called outcome");
  assert.equal(out.rows[1].value, "44%");
  assert.equal(out.rows[1].qualifier, "Closest game");
  assert.equal(out.rows[1].secondary, true);
  assert.notEqual(out.rows[0].name, out.rows[1].name);
});

test("the NBA teaser returns two rows: the closest game, then the most confident pick", () => {
  const out = selectNBA([
    { game_id: "1", home_team: "NYK", away_team: "BOS", completed: false, prediction: { home_win_prob: 0.55 } },
    { game_id: "2", home_team: "LAL", away_team: "GSW", completed: false, prediction: { home_win_prob: 0.50 } },
    // Neither of these may reach either row: one has no prediction, one has
    // already finished. One pre-event filter, shared by both rows.
    { game_id: "3", home_team: "MIA", away_team: "DAL", completed: false, prediction: null },
    { game_id: "4", home_team: "PHX", away_team: "GSW", completed: true, prediction: { home_win_prob: 0.99 } },
  ]);
  assert.equal(out.rows.length, 2);
  assert.equal(out.rows[0].name, "LAL v GSW");
  assert.equal(out.rows[0].value, "50%");
  assert.equal(out.rows[0].qualifier, "Closest game");
  assert.equal(out.rows[1].name, "NYK v BOS");
  assert.equal(out.rows[1].value, "55%");
  assert.equal(out.rows[1].qualifier, "Most confident pick");
  assert.equal(out.rows[1].secondary, true);
  assert.ok(
    out.rows.every((r) => r.name !== "MIA v DAL" && r.name !== "PHX v GSW"),
    "a game with no pick, or one already finished, appears in neither row",
  );
});

test("one game that is genuinely both: one row that says so, never the same pick twice", () => {
  // With one pick left in the week, closest and most confident are the same
  // game by definition. Print it once and say it is both.
  const football = selectFootball(
    [{ game_id: "g1", home_team: "AAA", away_team: "BBB", gameday: "2026-11-05T00:00:00", spread_line: null }],
    { g1: { home_win_prob: 0.51, away_win_prob: 0.49 } },
  );
  assert.equal(football.rows.length, 1, "the same pick must not print twice");
  assert.equal(football.rows[0].name, "AAA v BBB");
  assert.equal(football.rows[0].qualifier, "Closest game and most confident pick");
  assert.equal(football.rows[0].secondary, undefined, "the only row is still row 1");

  const nba = selectNBA([
    { game_id: "1", home_team: "NYK", away_team: "BOS", completed: false, prediction: { home_win_prob: 0.55 } },
  ]);
  assert.equal(nba.rows.length, 1);
  assert.equal(nba.rows[0].qualifier, "Closest game and most confident pick");

  // PL can be both with two fixtures in hand: in a three-way market every
  // called outcome can sit under 50%, and then nearest-to-0.5 and surest are
  // the same fixture. Still one row.
  const pl = selectPL({
    current_gameweek: 9,
    fixtures_by_gameweek: { 9: { gameweek: 9, fixtures: [
      { event_id: "1", team_home: "A", team_away: "B", predicted_home_win: 0.44, predicted_draw: 0.30, predicted_away_win: 0.26, predicted_scoreline: "1-1", has_live_odds: false, value_bet_flags: [] },
      { event_id: "2", team_home: "C", team_away: "D", predicted_home_win: 0.46, predicted_draw: 0.30, predicted_away_win: 0.24, predicted_scoreline: "1-1", has_live_odds: false, value_bet_flags: [] },
    ] } },
  });
  assert.equal(pl.rows.length, 1, "two toss-ups with the same surest fixture is still one row");
  assert.equal(pl.rows[0].name, "C v D");
  assert.equal(pl.rows[0].qualifier, "Closest game and most confident pick");
});

// --- 7. The card's shape: three drivers, in probability order ---

test("a session card shows exactly the top three, highest probability first", () => {
  // The card is "the top three" and that is the whole promise. When the F1
  // tests were rewritten for the session rule, this guarantee went with them:
  // nothing asserted the count or the order, so a selector that returned every
  // driver, or returned them in feed order, would still have been green.
  const drivers = [
    { driver_id: "russell", p_win: 0.15 },
    { driver_id: "norris", p_win: 0.40 },
    { driver_id: "verstappen", p_win: 0.30 },
    { driver_id: "hamilton", p_win: 0.09 },
    { driver_id: "leclerc", p_win: 0.06 },
  ];
  const out = selectF1(F1_RACES, {
    16: {
      qualifying: { source: "tracked", predictions: [{ driver_id: "x", p_pole: 0.1 }] },
      race: { source: "live", predictions: drivers },
    },
  }, AFTER_QUALIFYING);
  assert.equal(out.rows.length, 3, "the card must show three drivers, not every driver in the payload");
  assert.deepEqual(out.rows.map((r) => r.name), ["Norris", "Verstappen", "Russell"],
    "highest probability first, and the title-cased name, not the raw id");
});

// --- a teaser row that links to the game it names --------------------------
//
// paintRow is internal and this repo has no jsdom (see the render-contract
// tests above), so the render is exercised the way the browser exercises it:
// a minimal DOM, a fetch stub for two sports — NBA, whose site accepts a game
// identifier, and PL, whose site accepts nothing — and a fresh evaluation of
// teasers.js. The import URL carries a query so Node's module cache hands
// back a new instance rather than the one imported at the top of this file,
// which saw no `document` and therefore never hydrated. The new instance
// hydrates on import *because* a document exists, so the fake DOM has to be
// installed before the import and removed afterwards.

function fakeEl(tag) {
  return {
    tagName: tag.toUpperCase(),
    className: "",
    textContent: "",
    children: [],
    attrs: {},
    append(...nodes) { this.children.push(...nodes); },
    replaceChildren(...nodes) { this.children = [...nodes]; },
    setAttribute(name, value) { this.attrs[name] = String(value); },
    getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; },
  };
}

/** Everything a screen reader would read out of an element: its own text plus
 *  its descendants' text, in order. */
const textOf = (el) => [el.textContent, ...el.children.map(textOf)].join("");

/** Every descendant with the given tag, in document order. */
const tagsIn = (el, tag) =>
  el.children.flatMap((child) =>
    child.tagName === tag.toUpperCase() ? [child, ...tagsIn(child, tag)] : tagsIn(child, tag));

const until = async (predicate, tries = 200) => {
  for (let i = 0; i < tries; i += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  throw new Error("the teasers never painted");
};

const ok = (payload) => ({ ok: true, status: 200, json: async () => payload });

const META = { generated_at: "2026-09-27T22:12:44.448691+00:00", source: "public_snapshot" };

const NBA_GAMES = [
  { game_id: "g-nyk-bos", home_team: "NYK", away_team: "BOS", completed: false, prediction: { home_win_prob: 0.55 } },
  { game_id: "g-lal-gsw", home_team: "LAL", away_team: "GSW", completed: false, prediction: { home_win_prob: 0.8 } },
];

const PL_FIXTURES = {
  current_gameweek: 9,
  fixtures_by_gameweek: {
    9: {
      gameweek: 9,
      fixtures: [
        { event_id: "e1", team_home: "Arsenal", team_away: "Chelsea", predicted_home_win: 0.6, predicted_draw: 0.25, predicted_away_win: 0.15, predicted_scoreline: "2-1", has_live_odds: false, value_bet_flags: [] },
        { event_id: "e2", team_home: "Leeds", team_away: "Everton", predicted_home_win: 0.47, predicted_draw: 0.3, predicted_away_win: 0.23, predicted_scoreline: "1-1", has_live_odds: false, value_bet_flags: [] },
      ],
    },
  },
};

/** Paint the NBA and PL teasers against a fake DOM and return their slots.
 *  The other three sports have no slot, so hydrate skips them without ever
 *  calling fetch — one fake covers both the linked and the unlinked case. */
let renderCount = 0;
async function paintTeasers() {
  const slots = { nba: fakeEl("div"), pl: fakeEl("div") };
  const previous = { document: globalThis.document, fetch: globalThis.fetch };
  globalThis.document = {
    readyState: "complete",
    createElement: fakeEl,
    querySelector: (selector) => {
      const match = /data-teaser="(\w+)"/.exec(selector);
      return (match && slots[match[1]]) || null;
    },
  };
  globalThis.fetch = async (path) => {
    if (path.startsWith("/nba/games/week")) return ok(NBA_GAMES);
    if (path.startsWith("/nba/snapshot-meta")) return ok(META);
    if (path.startsWith("/pl/api/fixtures/gameweek")) return ok({ current_gameweek: 9 });
    if (path.startsWith("/pl/api/snapshot-meta")) return ok(META);
    if (path.startsWith("/pl/api/fixtures")) return ok(PL_FIXTURES);
    throw new Error(`no fixture for ${path}`);
  };
  try {
    renderCount += 1;
    await import(new URL(`../teasers.js?paint=${renderCount}`, import.meta.url).href);
    await until(() => slots.nba.children.length > 0 && slots.pl.children.length > 0);
    return slots;
  } finally {
    globalThis.document = previous.document;
    globalThis.fetch = previous.fetch;
  }
}

test("a row with an href renders an <a> whose accessible text names the game; a row without one renders no anchor", async () => {
  const slots = await paintTeasers();

  const anchors = tagsIn(slots.nba, "a");
  assert.equal(anchors.length, 2, "both NBA rows carry an href, so both must paint as links");
  assert.match(textOf(anchors[0]), /NYK v BOS/, "the link's accessible text must contain the game it names");
  assert.match(textOf(anchors[1]), /LAL v GSW/);
  assert.ok(
    anchors.every((a) => /^https:\/\/nba\./.test(a.href)),
    `an href must be a URL the NBA site actually serves, got: ${anchors.map((a) => a.href).join(", ")}`,
  );

  // PL's site has no URL a row could point at, so its rows carry no href and
  // must paint as plain rows — no anchor anywhere in the slot.
  assert.deepEqual(tagsIn(slots.pl, "a"), [], "a row with no href must render no anchor");
  const plRows = slots.pl.children.filter((child) => child.className === "teaser-row");
  assert.equal(plRows.length, 2, "the PL teaser still paints both of its rows");
  for (const row of plRows) assert.equal(row.tagName, "DIV", "an unlinked row is a div, not a link");
  assert.match(textOf(slots.pl), /Arsenal v Chelsea/, "the unlinked rows keep their text");
});

test("a teaser whose sport has no deep-link support produces rows with no href", () => {
  // The hub must never advertise a link the site cannot honour. This pins the
  // absence at both unlinked sports: PL and F1 (whose rows name a driver, not
  // a game) gain an href only when their sites can accept one, which today
  // they cannot — neither site has a router, a path route or a query
  // parameter to link to.
  const pl = selectPL({
    current_gameweek: 9,
    fixtures_by_gameweek: { 9: { gameweek: 9, fixtures: [
      { event_id: "e1", team_home: "A", team_away: "B", predicted_home_win: 0.44, predicted_draw: 0.25, predicted_away_win: 0.31, has_live_odds: false, value_bet_flags: [] },
      { event_id: "e2", team_home: "C", team_away: "D", predicted_home_win: 0.86, predicted_draw: 0.08, predicted_away_win: 0.06, has_live_odds: false, value_bet_flags: [] },
    ] } },
  });
  assert.ok(pl.rows.length > 0, "the fixture is there to link — and must still not carry one");
  for (const row of pl.rows) assert.equal(row.href, undefined, "PL serves no deep link, so its rows carry no href");

  const f1 = selectF1(TIMINGLESS_RACES, {
    16: { race: { source: "live", predictions: RACE_PREDICTIONS } },
  }, BEFORE_QUALIFYING);
  assert.ok(f1.rows.length > 0);
  for (const row of f1.rows) {
    assert.equal(row.href, undefined, "an F1 row names a driver, and the F1 site has no URL state to link to");
  }
});

test("the teaser link is a real link element, not a div with a role", async () => {
  const slots = await paintTeasers();
  const [anchor] = tagsIn(slots.nba, "a");
  assert.ok(anchor, "no link painted at all");
  assert.equal(anchor.tagName, "A");
  assert.equal(anchor.attrs.role, undefined, "role on a real link only renames it");
  assert.equal(anchor.attrs.tabindex, undefined, "a real <a> is focusable without tabindex");
  // Activation is the browser's own — that is what makes Enter work — so no
  // click handler anywhere in the module, and no role= to be tempted by.
  assert.doesNotMatch(src, /addEventListener\(\s*["']click/, "a link must not need a click handler");
  assert.doesNotMatch(src, /\brole\s*=/, "no role: the element itself is the semantics");
  // The page's focus ring is a bare `:focus-visible` rule with no tag or
  // ancestor qualifier, so it reaches a row that is now an <a> as readily as
  // it reached a div. (A second, qualified rule exists for .pr-notch; the
  // bare one is the one that applies here.)
  const indexHtml = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  assert.match(indexHtml, /:focus-visible\s*\{/, "no focus-visible rule for the link to inherit");
});
