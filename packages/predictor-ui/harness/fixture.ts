/**
 * The ONE fixture for the 2026-09-30 spec mocks. Not a shipped surface.
 *
 * Review round 2 found the draft violating its own rules: the picks mock
 * ranked an OUT player, mixed a rebounds row under a points heading, and
 * carried the same player's yardage as 96 in one mock and 84 in another.
 * Re-shooting after those fixes caught a fifth, of the same family: with
 * one `value` per player, a player's RUSH YARDS were rendered as his
 * anytime-TD probability — "9600%". So the numbers are keyed BY CATEGORY,
 * not by player, and the assertion range-checks each row against the kind
 * of its category (a probability cannot exceed 1).
 *
 * Every figure any mock renders is READ FROM HERE.
 * `assertFixtureConsistency()` runs at load in insight.tsx and throws,
 * naming every problem, rather than rendering a mock that lies.
 */

export type Category =
  | "Anytime TD"
  | "Rush yds"
  | "Points"
  | "Rebounds";

export type Player = {
  key: string;
  name: string;
  team: string;
  /** The model's own number PER CATEGORY — the ranking key for that list. */
  values: Partial<Record<Category, number>>;
  /** Bucket hit-rate context for a probability row: hits over n. */
  bucket?: { hits: number; n: number };
  /** In-sample MAE per category, used as the ± on a projection row. */
  mae?: Partial<Record<Category, number>>;
  /** In the injury report: excluded from every ranking (§D). */
  out?: boolean;
};

/** The one game. GB at ATL, week 6. */
export const FIX = {
  home: "GB",
  away: "ATL",
  homeWinProb: 0.72,
  awayWinProb: 0.28,
  spreadLine: -4.5, // GB −4.5, home frame
  modelMargin: -6.1, // home minus away: model wants 1.6 more than market
  predictedTotal: 42.1,
  totalLine: 43.5,
  recordHits: 11,
  recordSettled: 15,
  pick: "Green Bay",
  /** The gap between the model's margin and the line, derived once. */
  get edge() {
    return Math.round((this.modelMargin - this.spreadLine) * 10) / 10;
  },
} as const;

/** Every player figure in every mock, keyed once. */
export const PLAYERS: Record<string, Player> = {
  jacobs: {
    key: "jacobs",
    name: "J. Jacobs",
    team: FIX.home,
    values: { "Anytime TD": 0.41, "Rush yds": 78 },
    bucket: { hits: 0.44, n: 112 },
    mae: { "Rush yds": 18 },
    out: true, // official injury report — he is OUT, so he is not ranked
  },
  robinson: {
    key: "robinson",
    name: "B. Robinson",
    team: FIX.away,
    values: { "Anytime TD": 0.38, "Rush yds": 96 },
    bucket: { hits: 0.33, n: 140 },
    mae: { "Rush yds": 18 },
  },
  wilson: {
    key: "wilson",
    name: "E. Wilson",
    team: FIX.home,
    values: { "Anytime TD": 0.24, "Rush yds": 41 },
    bucket: { hits: 0.24, n: 98 },
    mae: { "Rush yds": 18 },
  },
  love: {
    key: "love",
    name: "J. Love",
    team: FIX.home,
    values: { "Anytime TD": 0.22 },
    bucket: { hits: 0.24, n: 98 },
  },
  tatum: {
    key: "tatum",
    name: "J. Tatum",
    team: "BOS",
    values: { Points: 27.4 },
    mae: { Points: 4.1 },
  },
  brown: {
    key: "brown",
    name: "J. Brown",
    team: "BOS",
    values: { Points: 24.9 },
    mae: { Points: 4.1 },
  },
  adebayo: {
    key: "adebayo",
    name: "B. Adebayo",
    team: "MIA",
    values: { Rebounds: 10.2 },
    mae: { Rebounds: 2.3 },
  },
};

/** Categories that rank by probability (share bar) vs by projection (±). */
export const CATEGORY_KIND: Record<Category, "probability" | "projection"> = {
  "Anytime TD": "probability",
  "Rush yds": "projection",
  Points: "projection",
  Rebounds: "projection",
};

/** The categories shown. ONE category per list. */
export const LISTS: { category: Category; keys: string[] }[] = [
  // Jacobs is in the Anytime-TD pool but OUT: ranked() drops him, which is
  // the point of the rule — an out player leaves the ranking entirely.
  { category: "Anytime TD", keys: ["jacobs", "robinson", "love"] },
  { category: "Rush yds", keys: ["robinson", "wilson"] },
  { category: "Points", keys: ["tatum", "brown"] },
  { category: "Rebounds", keys: ["adebayo"] },
];

/** A player's number for a category, or undefined if that category is N/A. */
export function valueOf(p: Player, category: Category): number {
  const v = p.values[category];
  if (v === undefined) throw new Error(`${p.name} has no ${category} figure in the fixture`);
  return v;
}

/** Players eligible for ranking: out players are excluded (§D). */
export function ranked(category: Category): Player[] {
  const list = LISTS.find((l) => l.category === category);
  if (!list) throw new Error(`unknown category ${category}`);
  return list.keys
    .map((k) => {
      const p = PLAYERS[k];
      if (!p) throw new Error(`${category} references unknown player ${k}`);
      return p;
    })
    .filter((p) => !p.out && p.values[category] !== undefined)
    .sort((a, b) => valueOf(b, category) - valueOf(a, category));
}

/** Out players: shown once, below the lists, never inside a ranking. */
export function outPlayers(): Player[] {
  return Object.values(PLAYERS).filter((p) => p.out);
}

/**
 * The invariant the review asked for, as executable code. Throws on any
 * hand-typed figure that drifts from the object above — including a figure
 * of the wrong KIND, which is how "9600%" got onto the page.
 */
export function assertFixtureConsistency(
  rows: { category: Category; playerKey: string; value: number }[],
  boxRows: { key: string; values: number[] }[],
): void {
  const problems: string[] = [];

  for (const row of rows) {
    const p = PLAYERS[row.playerKey];
    if (!p) {
      problems.push(`${row.category} row names unknown player ${row.playerKey}`);
      continue;
    }
    if (p.out) {
      problems.push(`${p.name} is OUT but still appears in the ${row.category} list`);
    }
    const truth = p.values[row.category];
    if (truth === undefined) {
      problems.push(`${p.name} has no ${row.category} figure, yet a row shows ${row.value}`);
      continue;
    }
    if (truth !== row.value) {
      problems.push(
        `${row.category} row for ${p.name} shows ${row.value}, object says ${truth}`,
      );
    }
    // A row's number must be the KIND its category claims: a probability
    // cannot exceed 1, and a projection is not a fraction.
    if (CATEGORY_KIND[row.category] === "probability" && (row.value < 0 || row.value > 1)) {
      problems.push(
        `${p.name} shows ${row.value} as a ${row.category} probability — ${
          row.value > 1
            ? `a ${row.value > 1 ? "yardage" : "projection"} figure was read as a probability`
            : "probabilities are never negative"
        }`,
      );
    }
    if (CATEGORY_KIND[row.category] === "projection" && row.value < 0) {
      problems.push(`${p.name} shows a negative ${row.category} projection`);
    }
    // A probability row must carry its graded record, or say it has none.
    if (CATEGORY_KIND[row.category] === "probability" && !p.bucket) {
      problems.push(`${p.name} has a ${row.category} probability but no bucket record`);
    }
  }

  // One category per list: a row may only sit under a heading whose own key
  // list names that player, and each heading must carry exactly its ranked
  // players. (A player may legitimately appear under two headings — a RB is
  // both an anytime-TD candidate and a rushing candidate — so the rule is
  // about the row under the heading, never about the player.)
  for (const list of LISTS) {
    for (const row of rows.filter((r) => r.category === list.category)) {
      if (!list.keys.includes(row.playerKey)) {
        problems.push(
          `${PLAYERS[row.playerKey]?.name ?? row.playerKey} is shown under ${list.category}, ` +
            `which does not list them — one category per list`,
        );
      }
    }
    const expected = ranked(list.category).length;
    const got = rows.filter((r) => r.category === list.category).length;
    if (got !== expected) {
      problems.push(`${list.category}: ${got} rows shown, ${expected} ranked players`);
    }
  }

  // The same player's figure must agree wherever a mock shows it. The box
  // score's Yds column for a RB is his rush-yardage projection.
  for (const b of boxRows) {
    const p = PLAYERS[b.key];
    if (!p) {
      problems.push(`box score row ${b.key} is not in PLAYERS`);
      continue;
    }
    if (p.out) {
      problems.push(`${p.name} is out, so the box score must not project him`);
    }
    const truth = p.values["Rush yds"];
    if (truth === undefined) {
      problems.push(`${p.name} has no rush-yardage figure, yet the box score shows him`);
      continue;
    }
    if (b.values[0] !== truth) {
      problems.push(
        `box score shows ${p.name} ${b.values[0]}, picks show ${truth} — one fixture, one number`,
      );
    }
  }

  if (problems.length) {
    throw new Error(`fixture inconsistency:\n  - ${problems.join("\n  - ")}`);
  }
}