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
 *  would be the one thing this product must never do, so it is dropped.
 *
 *  This is a whitelist on purpose, not a blacklist of "rebuilt"/"backtest".
 *  The F1 API documents exactly four sources: "live" (computed fresh) and
 *  "tracked" (snapshotted before the session) are pre-event; "rebuilt"
 *  (written after it) and "backtest" (historical replay) are not. An
 *  unrecognised source is hidden rather than shown: a hidden row costs a
 *  visitor one line, while a wrongly-shown post-event pick is a lie. Do not
 *  "simplify" this to a blacklist — a genuinely new pre-event source must be
 *  added here deliberately, never discovered by a blank card. */
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

// --- rendering -------------------------------------------------------------
//
// The board is static HTML and renders with JavaScript disabled; this section
// only fills the five .teaser slots that already exist. Cards are never gated
// on a fetch, so with every API dead the page degrades to the working index
// of five sites it is today.

// selectFootball returns label: "" because one selector serves two sports, so
// each football entry carries its own label here -- otherwise the NFL and CFB
// teasers would render headerless.
const SPORTS = [
  { sport: "pl", run: plTeaser },
  { sport: "f1", run: f1Teaser },
  { sport: "nfl", run: () => footballTeaser("/nfl", "NFL") },
  { sport: "cfb", run: () => footballTeaser("/cfb", "CFB") },
  { sport: "nba", run: nbaTeaser },
];

async function getJSON(path) {
  const response = await fetch(path, { headers: { accept: "application/json" } });
  if (!response.ok) throw new Error(`${path} responded ${response.status}`);
  return response.json();
}

/** One teaser row. Text only -- no innerHTML anywhere in this file, because
 *  every string in it comes from an API payload. */
function paintRow(row) {
  const el = document.createElement("div");
  el.className = "teaser-row";
  const name = document.createElement("span");
  name.className = "teaser-name";
  name.textContent = row.name;
  const num = document.createElement("span");
  num.className = "teaser-num";
  num.textContent = row.value;
  el.append(name, num);
  if (row.sub) {
    const s = document.createElement("span");
    s.className = "teaser-note";
    s.textContent = row.sub;
    el.append(s);
  }
  // Edge is rendered only when the selector set it, and the selector sets it
  // only when a real line exists. An absent edge renders nothing at all --
  // there is no "no edge" placeholder, because that would read as a claim.
  if (row.edge) {
    const e = document.createElement("span");
    e.className = "teaser-edge";
    e.textContent = row.edge;
    el.append(e);
  }
  return el;
}

function paintNote(text) {
  const p = document.createElement("p");
  p.className = "teaser-note";
  p.textContent = text;
  return p;
}

function paint(slot, { label, rows, empty }, sub) {
  slot.replaceChildren();
  if (label) {
    const head = document.createElement("span");
    head.className = "teaser-label";
    head.textContent = label;
    slot.append(head);
  }
  for (const row of rows) slot.append(paintRow(row));
  if (empty) slot.append(paintNote(empty));
  if (sub) slot.append(paintNote(sub));
  // Cleared on every path out of this function, including the caller's
  // catch, so no region is ever left announced as loading.
  slot.setAttribute("aria-busy", "false");
}

/** Date line for a teaser, from the sport's /snapshot-meta endpoint.
 *
 *  The picks routes the hub calls return nested blocks (a week, a round) that
 *  drop the top-level `generated_at` of public_snapshot.json, so the picks
 *  payload itself carries no timestamp. Each sport's /snapshot-meta exists to
 *  answer exactly that question, and every per-sport fetcher below asks it.
 *  Two states are real and expected:
 *  - a valid `generated_at` (source "public_snapshot") -> the snapshot date;
 *  - source "live", or a null/absent `generated_at` -> the numbers were
 *    computed on request, not precomputed (a public deploy before its first
 *    snapshot). Rendered as the honest word "Live": never a dash, which reads
 *    as missing data, and never a fabricated date.
 *  A malformed `generated_at` falls back to "Live" rather than throwing or
 *  inventing a date -- a wrong date is worse than an honest word.
 *  A missing meta object (the caller never got one) returns "", so paint()'s
 *  `if (sub)` guard skips the line entirely: the picks render dateless.
 *  Pure over plain data, like the selectors above, hence unit-tested. */
export const freshness = (meta) => {
  if (!meta) return "";
  const at = meta.generated_at;
  if (typeof at === "string" && at) {
    const d = new Date(at);
    if (!Number.isNaN(d.getTime())) return `From the ${d.toISOString().slice(0, 10)} snapshot`;
  }
  return "Live";
};

/** Fetch one sport's snapshot-meta, never letting it break the picks.
 *
 *  This is a second request per sport and it can fail independently of the
 *  picks fetch, so it is caught here, separately: on failure the sport keeps
 *  its picks and simply shows no date line (""). What must never happen is
 *  the meta rejection propagating into hydrate()'s catch, which would blank
 *  the whole card -- picks with no date line are correct, nothing is not. */
async function metaSub(path) {
  try {
    return freshness(await getJSON(path));
  } catch {
    return "";
  }
}

async function plTeaser() {
  const week = await getJSON("/pl/api/fixtures/gameweek");
  const gw = week?.current_gameweek ?? week?.gameweek;
  const full = await getJSON("/pl/api/fixtures");
  const out = selectPL({ ...full, current_gameweek: gw });
  return [out, await metaSub("/pl/api/snapshot-meta")];
}

async function f1Teaser() {
  const races = await getJSON("/f1/api/races");
  const next = (races || []).find((r) => !r.completed);
  // The source (tracked vs live) still matters on F1, so it stays -- folded
  // onto the same one-line `sub` as the date, joined only when both exist.
  // If they ever compete for space the date wins: drop the source, not it.
  if (!next) return [selectF1(races, {}), await metaSub("/f1/api/snapshot-meta")];
  const prediction = await getJSON(`/f1/api/races/${next.season}/${next.round}/prediction`);
  const source = prediction.source ? `Source: ${prediction.source}` : "";
  const date = await metaSub("/f1/api/snapshot-meta");
  return [selectF1(races, { [next.round]: prediction }), [date, source].filter(Boolean).join(" · ")];
}

async function footballTeaser(base, label) {
  const week = await getJSON(`${base}/api/current-week`);
  const games = await getJSON(`${base}/api/games?season=${week.season}&week=${week.week}`);
  const predictions = await getJSON(`${base}/api/predictions/${week.season}/${week.week}/batch`);
  // base is "/nfl" or "/cfb" (see SPORTS), so this one line fetches
  // "/nfl/api/snapshot-meta" or "/cfb/api/snapshot-meta" respectively.
  return [{ ...selectFootball(games, predictions), label }, await metaSub(`${base}/api/snapshot-meta`)];
}

async function nbaTeaser() {
  const games = await getJSON(`/nba/api/games/week?start=${new Date().toISOString().slice(0, 10)}`);
  return [selectNBA(games), await metaSub("/nba/api/snapshot-meta")];
}

function hydrate() {
  for (const { sport, run } of SPORTS) {
    const slot = document.querySelector(`.teaser[data-teaser="${sport}"]`);
    if (!slot) continue;
    // Each sport is its own promise. Promise.all would short-circuit on the
    // first rejection and leave the rest of the board empty, which is the
    // failure this file is written to avoid.
    run(sport)
      .then(([out, sub]) => paint(slot, out, sub))
      .catch((err) => {
        slot.replaceChildren();
        const note = document.createElement("p");
        note.className = "teaser-note";
        note.textContent = "Picks unavailable right now.";
        slot.append(note);
        slot.setAttribute("aria-busy", "false");
        console.warn(`hub teaser ${sport} failed`, err);
      });
  }
}

// Guarded so the Node test suite can import this module's pure selectors
// without a DOM. In a browser document always exists: type="module" is
// deferred by default, so readyState here is never "loading" in practice,
// but the branch costs nothing and covers a script moved to <head>.
if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hydrate, { once: true });
  } else {
    hydrate();
  }
}
