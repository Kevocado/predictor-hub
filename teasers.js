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

// The session order for a sprint weekend: sprint qualifying, sprint,
// qualifying, then race. A normal weekend drops the two sprint sessions.
// This order is used by findNextSession to pick the earliest future
// session regardless of which prediction data happens to exist.
const SESSION_ORDER = ["sprint_qualifying", "sprint", "qualifying", "race"];

// Labels for the session column on the card. The label tells the
// visitor which market the probability refers to.
const SESSION_LABELS = {
  sprint_qualifying: "Sprint Qualifying",
  sprint: "Sprint",
  qualifying: "Qualifying",
  race: "Race",
};

// Session types that carry qualifying-style payloads: p_pole, p_top_3,
// p_top_10 — no p_win. These sessions lead with pole chance.
const QUALIFYING_SESSIONS = new Set(["sprint_qualifying", "qualifying"]);

/** The sessions a round actually runs: a sprint weekend has four, a normal
 *  weekend has two. Both the timing count and the clock walk below use this,
 *  so they can never disagree about what a round contains. */
function sessionsOf(race) {
  return race.is_sprint_weekend
    ? SESSION_ORDER
    : SESSION_ORDER.filter((s) => s === "qualifying" || s === "race");
}

/** A session time the clock can actually read: present and parseable.
 *  session_datetime absent (the field is not deployed) and session_datetime
 *  present-but-garbage are the same incapability, not two different ones. */
const usableTime = (value) =>
  typeof value === "string" && value !== "" && !Number.isNaN(new Date(value).getTime());

/** How many of this round's sessions carry a usable time. This count, and
 *  only this count, decides which of the two branches below runs. */
function usableTimeCount(race) {
  const dt = race.session_datetime || {};
  return sessionsOf(race).filter((s) => usableTime(dt[s])).length;
}

/** Find the session the card should show, walking the uncompleted races.
 *
 *  TWO FAILURES, BOTH OF WHICH LEAVE THE CLOCK WITH NO FUTURE SESSION, AND
 *  THEY ARE NOT THE SAME FAILURE — so they never share a branch:
 *
 *  1. TIMING IS MISSING. No session of this round has a usable
 *     session_datetime, so the API cannot answer "what is next" at all.
 *     (Today this is the production state: the field is committed to the API
 *     but the hub's F1 container re-fetches its snapshot from GitHub main,
 *     where it is not merged, so every value is null.) An unanswerable
 *     question gets the honest older answer — the race card, top three by
 *     p_win — because a blank card tells a visitor nothing and the older
 *     answer was true. This is a capability gap, not a schedule.
 *  2. TIMING IS PRESENT AND THE SESSION HAS PASSED. The clock did answer,
 *     and its answer is "move on": skip to the next session, and if the race
 *     is next, show the race. Falling back to the race here — as case 1 does
 *     — would skip qualifying every single week, because the snapshot ships
 *     race predictions for future rounds with source: live and any
 *     availability-based rule jumps straight to the race. No fallback in
 *     this case: an empty clock with readable times means the sessions are
 *     behind us, not that we lack the data.
 *
 *  The branch is decided by COUNTING usable times (zero vs. not zero), never
 *  by "the clock came up empty" — that predicate is true in both cases and
 *  is exactly what must not be used. Returns { race, session }, or null when
 *  every uncompleted round has readable timing and all of it has passed. */
function findNextSession(races, now) {
  const uncompleted = (races || []).filter((r) => !r.completed);
  for (const race of uncompleted) {
    // Case 1 — capability gap: this round cannot say when anything is, so
    // the clock is not consulted. Its race card, as it was before the field
    // existed.
    if (usableTimeCount(race) === 0) return { race, session: "race" };
    // Case 2 — readable timing: the earliest session still ahead on the
    // clock wins, and a session whose time has gone is never a candidate.
    const dt = race.session_datetime;
    for (const session of sessionsOf(race)) {
      if (usableTime(dt[session]) && new Date(dt[session]) > now) return { race, session };
    }
  }
  return null;
}

/** Returns the session label for display on the card. */
function sessionLabel(session) {
  return SESSION_LABELS[session] || session;
}

/** Returns the field name that is the headline probability for a session
 *  type. Race and sprint use p_win; qualifying uses p_pole. Returns
 *  null if the session type has no headline probability field at all. */
function headlineField(session) {
  return QUALIFYING_SESSIONS.has(session) ? "p_pole" : "p_win";
}

/** The F1 card: the session findNextSession chose, top three by that
 *  session's headline market.
 *
 *  findNextSession returns a race for two different reasons (see its
 *  comment): readable timing says the race is next, or there is no readable
 *  timing and the race card is the honest older answer. This function does
 *  not care which — the market, the source check and the three-driver shape
 *  are the same either way, which is the point of the fallback: the card
 *  stays a normal, honest card. */
export function selectF1(races, predictions, now = Date.now()) {
  const next = findNextSession(races, now);
  if (!next) return { label: "Formula 1", rows: [], empty: "No sessions left this season" };
  const { race, session } = next;
  const sessionPredictions = (predictions || {})[race.round]?.[session];
  if (!sessionPredictions || !isPreEvent(sessionPredictions.source)) {
    return { label: `${race.race_name} — ${sessionLabel(session)}`, rows: [], empty: "No pre-event pick for this session yet" };
  }
  const preds = sessionPredictions.predictions || [];
  if (!preds.length) return { label: `${race.race_name} — ${sessionLabel(session)}`, rows: [], empty: `No driver predictions yet` };
  const field = headlineField(session);
  // If the session's own headline probability field is absent from the
  // data, we do not fall back to p_win — a qualifying card must not
  // show a win figure. Say the card has no picks.
  if (!preds.some((d) => typeof d[field] === "number" && Number.isFinite(d[field]))) {
    return { label: `${race.race_name} — ${sessionLabel(session)}`, rows: [], empty: `No ${sessionLabel(session.toLowerCase())} picks yet` };
  }
  const rows = preds
    .slice()
    .sort((a, b) => (b[field] ?? -Infinity) - (a[field] ?? -Infinity))
    .slice(0, 3)
    .map((d) => {
      const row = { name: driverName(d.driver_id, d.driver_name), value: pct(d[field]) };
      if (QUALIFYING_SESSIONS.has(session)) {
        row.sub = `Top 3 ${pct(d.p_top_3)}`;
      } else {
        row.sub = `Podium ${pct(d.p_podium)}`;
      }
      return row;
    });
  return { label: `${race.race_name} — ${sessionLabel(session)}`, rows, empty: rows.length ? "" : `No ${sessionLabel(session.toLowerCase())} picks yet` };
}

// --- the two-row teasers (non-F1) -------------------------------------------
//
// Each non-F1 teaser answers two questions about ONE payload: which game is
// closest to a coin flip, and which pick is the most confident. The rows must
// not read as one pick, so each carries a short qualifier saying why it is on
// the card, and the second row is marked `secondary` so paintRow draws it
// without the accent number. F1 keeps its three drivers and gains no second
// group — that is its own shape.

/** Row qualifiers. Exact strings, asserted in the tests: a reader who cannot
 *  tell the two rows apart takes them for the same pick twice. */
const QUALIFIER_CLOSEST = "Closest game";
const QUALIFIER_CONFIDENT = "Most confident pick";

/** Both criteria landed on one fixture. Say so in one row — printing the same
 *  pick twice reads as a bug, and calling it only one of the two hides that it
 *  is genuinely both. */
const QUALIFIER_BOTH = "Closest game and most confident pick";

/** Assemble a selector's two rows. `first` is the row this sport already
 *  showed (unchanged), `second` is the other view of the same payload, and
 *  the qualifiers name which is which. Same fixture -> one row carrying both
 *  qualifiers, never two identical rows.
 *
 *  Identity is the name the reader sees: both rows are built from one
 *  already-filtered list, so equal names mean the same fixture, and a payload
 *  that carries no id at all cannot collapse two different games into one. */
function pairUp(first, second, qualifierFirst, qualifierSecond) {
  if (first.name === second.name) return [{ ...first, qualifier: QUALIFIER_BOTH }];
  return [
    { ...first, qualifier: qualifierFirst },
    { ...second, qualifier: qualifierSecond, secondary: true },
  ];
}

export function selectPL(payload) {
  const week = (payload?.fixtures_by_gameweek || {})[payload?.current_gameweek];
  // One pre-event filter, one candidate list: both rows are drawn from it, so
  // the second row can never surface a fixture this one already rejected.
  const fixtures = (week?.fixtures || []).filter((f) => !f.finished);
  if (!fixtures.length) return { label: "Premier League", rows: [], empty: "No fixtures this gameweek" };
  // Confidence in a three-way market: the probability of the outcome the
  // model actually calls. Row 1 is the fixture it is most sure about — the
  // row this teaser has always shown, unchanged.
  const top = (f) => Math.max(f.predicted_home_win, f.predicted_draw, f.predicted_away_win);
  const confident = fixtures.slice().sort((a, b) => top(b) - top(a))[0];
  // Row 2: the fixture nearest a toss-up, the same idea as |p - 0.5| for a
  // two-way market, read off the called outcome.
  const closest = fixtures.slice().sort((a, b) => Math.abs(top(a) - 0.5) - Math.abs(top(b) - 0.5))[0];
  const row = (strongest) => {
    const pick =
      strongest.predicted_draw >= Math.max(strongest.predicted_home_win, strongest.predicted_away_win)
        ? "Draw"
        : strongest.predicted_home_win >= strongest.predicted_away_win
          ? strongest.team_home
          : strongest.team_away;
    const out = {
      name: `${strongest.team_home} v ${strongest.team_away}`,
      value: pct(top(strongest)),
      pick,
      sub: strongest.predicted_scoreline ? `Most likely score ${strongest.predicted_scoreline}` : "",
    };
    // An edge is only ever shown when the feed says a real price exists —
    // checked per fixture, so each row carries only its own line.
    if (strongest.has_live_odds && (strongest.value_bet_flags || []).length) {
      out.edge = `Value: ${strongest.value_bet_flags.join(", ").replace(/_/g, " ")}`;
    }
    return out;
  };
  return {
    label: "Premier League",
    rows: pairUp(row(confident), row(closest), QUALIFIER_CONFIDENT, QUALIFIER_CLOSEST),
    empty: "",
  };
}

// How sure a two-way pick is: the model's own probability for whichever side
// it favours, so 0.5 is a coin flip and 1.0 is a certainty. Used for the
// most-confident row; the closest row keeps measuring |home_win_prob - 0.5|.
const confidence = (p) => Math.max(p.home_win_prob, p.away_win_prob ?? 1 - p.home_win_prob);

export function selectFootball(games, predictions) {
  const upcoming = (games || []).filter((g) => g.home_score == null && g.away_score == null);
  if (!upcoming.length) return { label: "", rows: [], empty: "No games left this week" };
  // One candidate list for both rows: the pre-event filter above is the only
  // eligibility rule this card has, and the second row does not get its own.
  const candidates = upcoming
    .map((g) => ({ game: g, p: (predictions || {})[g.game_id] }))
    .filter((x) => x.p && Number.isFinite(x.p.home_win_prob));
  if (!candidates.length) return { label: "", rows: [], empty: "No picks for this week's games yet" };
  // Row 1, unchanged: the game closest to a coin flip.
  const closest = candidates
    .slice()
    .sort((a, b) => Math.abs(a.p.home_win_prob - 0.5) - Math.abs(b.p.home_win_prob - 0.5))[0];
  // Row 2: the week's most confident call — a different question about the
  // same games, which is why it is a second row and not a second fetch.
  const confident = candidates.slice().sort((a, b) => confidence(b.p) - confidence(a.p))[0];
  const row = ({ game, p }) => {
    const out = {
      name: `${game.home_team} v ${game.away_team}`,
      value: pct(Math.max(p.home_win_prob, p.away_win_prob)),
      pick: p.home_win_prob >= p.away_win_prob ? game.home_team : game.away_team,
      sub: game.gameday ? new Date(game.gameday).toUTCString().slice(0, 22) : "",
    };
    // A line on some other game says nothing about this one — each row only
    // ever carries the line of the game it names.
    if (game.spread_line != null) out.edge = `Line ${game.home_team} ${game.spread_line}`;
    return out;
  };
  return {
    label: "",
    rows: pairUp(row(closest), row(confident), QUALIFIER_CLOSEST, QUALIFIER_CONFIDENT),
    empty: "",
  };
}

export function selectNBA(games) {
  // One filter, one list, both rows: not completed and carrying a usable
  // prediction — the card's only pre-event rule, reused rather than repeated.
  const open = (games || []).filter(
    (g) => !g.completed && g.prediction && Number.isFinite(g.prediction.home_win_prob),
  );
  if (!open.length) return { label: "NBA", rows: [], empty: "No games with a pick right now" };
  // Row 1, unchanged: the game closest to a coin flip.
  const closest = open
    .slice()
    .sort((a, b) => Math.abs(a.prediction.home_win_prob - 0.5) - Math.abs(b.prediction.home_win_prob - 0.5))[0];
  // Row 2: the most confident pick over the same open games.
  const confident = open.slice().sort((a, b) => confidence(b.prediction) - confidence(a.prediction))[0];
  const row = (game) => {
    const p = game.prediction;
    return {
      name: `${game.home_team} v ${game.away_team}`,
      value: pct(Math.max(p.home_win_prob, p.away_win_prob ?? 1 - p.home_win_prob)),
      pick: p.home_win_prob >= 0.5 ? game.home_team : game.away_team,
    };
  };
  return {
    label: "NBA",
    rows: pairUp(row(closest), row(confident), QUALIFIER_CLOSEST, QUALIFIER_CONFIDENT),
    empty: "",
  };
}

// --- rendering -------------------------------------------------------------
//
// The board is static HTML and renders with JavaScript disabled; this section
// only fills the five .teaser slots that already exist. Cards are never gated
// on a fetch, so with every API dead the page degrades to the working index
// of five sites it is today.

// Where a linked row sends a visitor. The five sport frontends are served on
// their own subdomains: the hub's host only proxies their APIs (the
// `handle_path /pl/*` etc. blocks in the VPS Caddyfile), so a hub-relative
// "/nba/?game=…" would be answered by the API proxy rather than the site —
// a 200 that is not the page, which is exactly the NBA "/api" failure this
// file's comments keep warning about. Absolute URLs, to the same host
// index.html's cards already link to. A real domain later has to change both
// files; hub.test.mjs pins the host in index.html, the tests here pin it here.
const HOST = "40-160-91-131.sslip.io";
const NBA_SITE = `https://nba.${HOST}`;
const SPORTS_SITE = `https://sports.${HOST}`;

/** Give each row the URL of the game it names, or no href at all.
 *
 *  Rows carry the game's *name* ("NYK v BOS") — the row contract gains `href`
 *  and nothing else, so there is no id on a row to build a URL from. The
 *  mapping from name back to id therefore happens here, in the fetcher, which
 *  is also the layer that knows which sport this is and therefore which URL
 *  shape it serves. A name that matches more than one game in the payload
 *  gets NO href: sending a row to one of two candidates is a link that looks
 *  right and opens the wrong game — worse than no link, and the same failure
 *  shape as a wrong API path returning a confident 200.
 *
 *  Sports whose site accepts no game identifier (PL and F1 today: neither has
 *  a router, a path route or a query parameter to send anyone to) never call
 *  this, so their rows keep rendering as plain, plainly unclickable rows. */
function linkRows(rows, games, urlPrefix) {
  const ids = new Map();
  for (const game of games) {
    const name = `${game.home_team} v ${game.away_team}`;
    ids.set(name, ids.has(name) ? null : game.game_id);
  }
  return rows.map((row) => {
    const id = ids.get(row.name);
    return id ? { ...row, href: `${urlPrefix}${encodeURIComponent(id)}` } : row;
  });
}

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
 *  every string in it comes from an API payload.
 *
 *  A row that carries an href paints as a real <a>: focusable, activatable
 *  with Enter, its own text (which contains the game) serving as its
 *  accessible name. A row without an href paints as the div it has always
 *  been — never a div with a click handler, and never a link-shaped thing
 *  that goes nowhere: a row that looks clickable and is not is worse than
 *  one that plainly is not. The page's bare `:focus-visible` rule reaches
 *  either element, so the focus ring needs nothing here. */
function paintRow(row) {
  const el = document.createElement(row.href ? "a" : "div");
  el.className = "teaser-row";
  if (row.href) el.href = row.href;
  const name = document.createElement("span");
  name.className = "teaser-name";
  name.textContent = row.name;
  const num = document.createElement("span");
  // Row 1 wears the accent number. Row 2 is the same payload seen a second
  // way and must not borrow that emphasis: it gets no class at all, so it
  // keeps the row's own --color-pr-text at the row's own size — the spec's
  // "same type, not the accent", and no new colour token, because hub tokens
  // are drift-tested against predictor-ui. The eye lands on row 1 first.
  if (!row.secondary) num.className = "teaser-num";
  num.textContent = row.value;
  el.append(name, num);
  // The qualifier leads the note line, so the two rows say why each is on
  // the card — "Closest game" versus "Most confident pick" — instead of
  // reading as one pick printed twice. F1 rows carry no qualifier and are
  // rendered exactly as before.
  const note = [row.qualifier, row.sub].filter(Boolean).join(" · ");
  if (note) {
    const s = document.createElement("span");
    s.className = "teaser-note";
    s.textContent = note;
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

/** Endpoints for each session type's prediction. */
const SESSION_ENDPOINTS = {
  sprint_qualifying: "sprint-qualifying-prediction",
  sprint: "sprint-prediction",
  qualifying: "qualifying-prediction",
  race: "prediction",
};

async function f1Teaser() {
  const races = await getJSON("/f1/api/races");
  const now = Date.now();
  const next = findNextSession(races, now);
  if (!next) return [selectF1(races, {}, now), await metaSub("/f1/api/snapshot-meta")];
  const { race, session } = next;
  const endpoint = SESSION_ENDPOINTS[session];
  // Catch the session prediction fetch so a 404 (e.g. a sprint
  // endpoint on a non-sprint weekend, or a prediction not yet
  // published) does not blank the card — the selector handles
  // missing data gracefully.
  const prediction = await getJSON(`/f1/api/races/${race.season}/${race.round}/${endpoint}`).catch(() => null);
  const source = prediction?.source ? `Source: ${prediction.source}` : "";
  const date = await metaSub("/f1/api/snapshot-meta");
  const preds = prediction ? { [race.round]: { [session]: prediction } } : {};
  return [selectF1(races, preds, now), [date, source].filter(Boolean).join(" · ")];
}

async function footballTeaser(base, label) {
  const week = await getJSON(`${base}/api/current-week`);
  const games = await getJSON(`${base}/api/games?season=${week.season}&week=${week.week}`);
  const predictions = await getJSON(`${base}/api/predictions/${week.season}/${week.week}/batch`);
  // base is "/nfl" or "/cfb" (see SPORTS), so base.slice(1) is the sport the
  // Sports site reads from ?sport= — the same value the family switcher
  // already puts in that parameter, and this one line fetches
  // "/nfl/api/snapshot-meta" or "/cfb/api/snapshot-meta" below. A row whose
  // game id cannot be resolved keeps no href (see linkRows) rather than
  // guessing one.
  const out = selectFootball(games, predictions);
  const rows = linkRows(out.rows, games, `${SPORTS_SITE}/?sport=${base.slice(1)}&game=`);
  return [{ ...out, label, rows }, await metaSub(`${base}/api/snapshot-meta`)];
}

// NBA is the one API with no /api prefix: its router is mounted at the app
// root (app.py does include_router(router) with no prefix, and the frontend's
// own client calls "/hub/track-record" and "/manifest" unprefixed). The other
// four all sit under /api. Guessing the prefix wrong is not a 404 here -- the
// NBA app mounts its SPA at "/" and answers any unknown path with the app
// shell and a 200, so a wrong prefix returns HTML and a 200 and fails quietly.
const NBA = "/nba";

async function nbaTeaser() {
  const games = await getJSON(`${NBA}/games/week?start=${new Date().toISOString().slice(0, 10)}`);
  // The NBA site takes ?game= on its "/" route, so a resolvable row links
  // there and an unresolvable one stays a plain row (see linkRows).
  const out = selectNBA(games);
  const rows = linkRows(out.rows, games, `${NBA_SITE}/?game=`);
  return [{ ...out, rows }, await metaSub(`${NBA}/snapshot-meta`)];
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
