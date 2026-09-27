// teasers.js — the picks shown under each card on the Predictor hub.
//
// Two rules govern this file. First, every selector is a pure function over
// plain data: it takes an API payload and returns { label, rows, empty }. It
// touches no DOM and fetches nothing, which is what makes it unit-testable
// without a browser. Second, "no data" is a normal answer, not an error:
// every selector returns { rows: [], empty: "a sentence" } rather than
// throwing, so an offseason sport never breaks the board.
//
// The honesty rules from PRODUCT.md apply to every number rendered here: only
// picks made before the event count, a rebuilt pick is shown and labelled but
// never presented as a call, and no edge is ever shown without a real line
// behind it.

/** A percentage for a visitor. Anything not a finite number is a dash, so a
 *  null or a NaN can never reach the page as "NaN%". */
export function pct(x) {
  if (typeof x !== "number" || !Number.isFinite(x)) return "—";
  return `${Math.round(x * 100)}%`;
}

/** Display name for a driver. Prefers the API's real name; otherwise derives
 *  one the same way the F1 site does, so the hub and the site cannot disagree
 *  about who a driver is. */
export function driverName(driverId, realName) {
  if (realName) return realName;
  return String(driverId || "")
    .split("_")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}

const byNumber = (key) => (a, b) => (b[key] ?? -Infinity) - (a[key] ?? -Infinity);

/** A rebuilt or backtest pick was made after the event. Showing it as a call
 *  would be the one thing this product must never do, so it is dropped. */
const isPreEvent = (source) => source === "tracked" || source === "live";

export function selectF1(races, predictions) {
  const race = (races || []).find((r) => !r.completed);
  if (!race) return { label: "Formula 1", rows: [], empty: "No races left this season" };
  const prediction = (predictions || {})[race.round];
  if (!prediction || !isPreEvent(prediction.source)) {
    return { label: race.race_name, rows: [], empty: "No pre-race pick for this race yet" };
  }
  const rows = (prediction.predictions || [])
    .slice()
    .sort(byNumber("p_win"))
    .slice(0, 3)
    .map((d) => ({
      name: driverName(d.driver_id, d.driver_name),
      value: pct(d.p_win),
      sub: `Podium ${pct(d.p_podium)}`,
    }));
  return { label: race.race_name, rows, empty: rows.length ? "" : "No driver predictions yet" };
}

export function selectPL(payload) {
  const week = (payload?.fixtures_by_gameweek || {})[payload?.current_gameweek];
  const fixtures = (week?.fixtures || []).filter((f) => !f.finished);
  if (!fixtures.length) return { label: "Premier League", rows: [], empty: "No fixtures this gameweek" };
  const strongest = fixtures
    .slice()
    .sort(
      (a, b) =>
        Math.max(b.predicted_home_win, b.predicted_draw, b.predicted_away_win) -
        Math.max(a.predicted_home_win, a.predicted_draw, a.predicted_away_win),
    )[0];
  const pick =
    strongest.predicted_draw >= Math.max(strongest.predicted_home_win, strongest.predicted_away_win)
      ? "Draw"
      : strongest.predicted_home_win >= strongest.predicted_away_win
        ? strongest.team_home
        : strongest.team_away;
  const value = Math.max(strongest.predicted_home_win, strongest.predicted_draw, strongest.predicted_away_win);
  const row = {
    name: `${strongest.team_home} v ${strongest.team_away}`,
    value: pct(value),
    pick,
    sub: strongest.predicted_scoreline ? `Most likely score ${strongest.predicted_scoreline}` : "",
  };
  // An edge is only ever shown when the feed says a real price exists.
  if (strongest.has_live_odds && (strongest.value_bet_flags || []).length) {
    row.edge = `Value: ${strongest.value_bet_flags.join(", ").replace(/_/g, " ")}`;
  }
  return { label: "Premier League", rows: [row], empty: "" };
}

export function selectFootball(games, predictions) {
  const upcoming = (games || []).filter((g) => g.home_score == null && g.away_score == null);
  if (!upcoming.length) return { label: "", rows: [], empty: "No games left this week" };
  const closest = upcoming
    .map((g) => ({ game: g, p: (predictions || {})[g.game_id] }))
    .filter((x) => x.p && Number.isFinite(x.p.home_win_prob))
    .sort((a, b) => Math.abs(a.p.home_win_prob - 0.5) - Math.abs(b.p.home_win_prob - 0.5))[0];
  if (!closest) return { label: "", rows: [], empty: "No picks for this week's games yet" };
  const { game, p } = closest;
  const row = {
    name: `${game.home_team} v ${game.away_team}`,
    value: pct(Math.max(p.home_win_prob, p.away_win_prob)),
    pick: p.home_win_prob >= p.away_win_prob ? game.home_team : game.away_team,
    sub: game.gameday ? new Date(game.gameday).toUTCString().slice(0, 22) : "",
  };
  // A line on some other game says nothing about this one.
  if (game.spread_line != null) row.edge = `Line ${game.home_team} ${game.spread_line}`;
  return { label: "", rows: [row], empty: "" };
}

export function selectNBA(games) {
  const open = (games || []).filter(
    (g) => !g.completed && g.prediction && Number.isFinite(g.prediction.home_win_prob),
  );
  if (!open.length) return { label: "NBA", rows: [], empty: "No games with a pick right now" };
  const game = open
    .slice()
    .sort((a, b) => Math.abs(a.prediction.home_win_prob - 0.5) - Math.abs(b.prediction.home_win_prob - 0.5))[0];
  const p = game.prediction;
  return {
    label: "NBA",
    rows: [{
      name: `${game.home_team} v ${game.away_team}`,
      value: pct(Math.max(p.home_win_prob, p.away_win_prob ?? 1 - p.home_win_prob)),
      pick: p.home_win_prob >= 0.5 ? game.home_team : game.away_team,
    }],
    empty: "",
  };
}
