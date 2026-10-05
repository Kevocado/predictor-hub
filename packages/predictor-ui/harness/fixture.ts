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
import type { Signal } from "../src";

/** A percentage in the words a headline uses, not the `pct()` dash form. `pct()`
 *  is for a live probability on a page, and it would turn the fixture's 0.6667
 *  into "67%" here and again in the component — two formats for one number in
 *  one file, which is how a mock starts disagreeing with the thing it mocks. */
const pctWord = (p: number): string => `${Math.round(p * 100)}%`;

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
  /** The gap between the model's margin and the line, in the home frame, derived
   *  once. Signed: `-1.6` means the model's margin is 1.6 pts further in the home
   *  team's favour than the line is. */
  get edge() {
    return Math.round((this.modelMargin - this.spreadLine) * 10) / 10;
  },
  /**
   * The same gap as a MAGNITUDE — "the model wants N points more than the line".
   *
   * A separate getter rather than `Math.abs(edge)` at the call site, because the
   * sign is a convention of the home frame and the magnitude is a different
   * question, and a signal's `gap` is the magnitude: the chip signs it with
   * `fmt.signed`, and a fixture that already carried the sign would render
   * "+−1.6". The comment above `edge` says which is which.
   */
  get edgePts() {
    return Math.abs(this.edge);
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

/**
 * The `Signal[]` this fixture feeds the shared `SignalRows` mocks.
 *
 * **Every figure here is read from `FIX` or derived from it**, the same rule the
 * player lists follow, so a signal mock cannot disagree with the tiles about the
 * same game. That is why `gap` is `FIX.edge` and not a retyped `1.6`.
 *
 * The `trust` row's RATE is the one figure `FIX` does not already carry — a
 * historical hit rate is not a property of this fixture — so it is declared here
 * with the bucket and the `n` that produce it, for the same reason
 * `PLAYERS[].bucket` exists. The bucket's own `model_prob` is NOT declared: it
 * is `FIX.homeWinProb`, because the probability is what selects the bucket and a
 * second copy of it is how the mock ended up claiming 66% under a tile that
 * said 72%.
 *
 * `BUCKET` is exported because the below-floor case is this row with a smaller
 * `n` and nothing else changed: a state of one fixture, not a second fixture.
 */
export const BUCKET = {
  /**
   * The model's own probability for this fixture — which is what SELECTS the
   * bucket, so it is `FIX.homeWinProb` and not a second number.
   *
   * A first draft put `0.66` here and labelled the bucket `60-70%` while the
   * tile above the signals says 72%. Both were "plausible" and they disagreed
   * about the same fixture, which is the one thing this file exists to prevent:
   * a reader comparing the two rows would find the mock claiming the model sits
   * in the 60s when the tile says it does not. CodeRabbit found it
   * (review comment 4171773474), and it was right.
   */
  model_prob: FIX.homeWinProb,
  /**
   * The bucket that probability falls in, DERIVED from it.
   *
   * Derived rather than typed so the two cannot drift again: the bounds are the
   * spec's own `n >= 30` bucket language read as ranges, and the edges are the
   * same ones `NFL_Predictor`'s `_TD_CONFIDENCE_BUCKETS` and `CFB_Predictor`'s
   * `_td_confidence_buckets` ship (the spike's open question 3 measured against
   * exactly those bounds).
   */
  // `toFixed(1)`, not `/ 10`: `0.8` from `(0.7 + 1) / 10` is `0.7999999999999999`,
  // and a bucket label is a word on the page, not a float. Rounding here is what
  // keeps the derived label equal to the one a test recomputes from `FIX`.
  label: (() => {
    const low = Math.floor(FIX.homeWinProb * 10);
    return `${(low / 10).toFixed(1)}-${((low + 1) / 10).toFixed(1)}`;
  })(),
  /** Hits over settled picks in that bucket. 5 of the 6 F1 buckets in the spike clear 30. */
  hits: 42,
  n: 61,
} as const;

/** The trust rate, as the spec's `trust` signal states it: a share, and the
 *  arithmetic done ONCE here so the bar and the headline cannot disagree. */
export const trustRate = BUCKET.hits / BUCKET.n;

export const SIGNALS: Signal[] = [
  {
    kind: "trust",
    sport: "nfl",
    game_id: "401671829",
    headline: {
      // 12 words exactly, so the harness shows the rule's own boundary and the
      // clipped case beside it is visibly a different thing.
      text: `At ${pctWord(BUCKET.model_prob)} this model has been right ${pctWord(trustRate)} of the time.`,
      // The figures the visual draws, plus the ones the headline only speaks.
      // `rate` is what the bar's width is; `model_prob` is not drawn by any
      // visual and exists so the headline's own number is in the payload.
      figures: { rate: trustRate, model_prob: BUCKET.model_prob },
    },
    n: BUCKET.n,
    source: `stored pre-kickoff picks, ${BUCKET.label} bucket`,
    as_of: "2026-09-30",
    strength: 0.8,
    pre_kickoff_only: true,
    visual: "reliability_bar",
  },
  {
    kind: "line_gap",
    sport: "nfl",
    game_id: "401671829",
    headline: {
      text: `Model wants ${FIX.edgePts} more than the line.`,
      // `FIX.edgePts` is the fixture's own derived gap as a magnitude, which is
      // the tile's arithmetic (`modelMargin − spreadLine`) without the home
      // frame's sign — see the two getters on `FIX`.
      figures: { gap: FIX.edgePts, model_margin: FIX.modelMargin, line: FIX.spreadLine },
    },
    n: null,
    source: `quoted spread at kickoff · ${FIX.home} ${FIX.spreadLine}`,
    as_of: "2026-10-04T16:00:00Z",
    strength: 0.6,
    pre_kickoff_only: true,
    visual: "delta_chip",
  },
];

/** Phase 2's absence row, in TWO sports, because the unit is the whole point.
 *
 *  `ABSENCE_SIGNAL` is NFL: a rush projection in YARDS, spelled out in the
 *  headline because the marker cannot know the unit. `PL_ABSENCE_SIGNAL` is the
 *  same shape carrying a share, spelled with a `%`. They are drawn identically,
 *  which IS the design: `figures.projection` is a magnitude in the sport's own
 *  units, and the headline is where the unit lives.
 *
 *  Both carry an `n` UNDER the rate floor -- 3 injured players and 1 -- and both
 *  draw. That is what `DRAWS_A_RATE.absence_strip === false` buys, and it is the
 *  thing a reader would notice first if it were wrong: a row about a handful of
 *  injured players is not a rate drawn from a handful of games. */
export const ABSENCE_SIGNAL: Signal = {
  kind: "absence",
  sport: "nfl",
  game_id: "401671829",
  headline: {
    text: "Out: J. Jacobs, our #2 rush projection (78 yds)",
    figures: { projection: 78 },
  },
  n: 3,
  source: "ESPN injury report, Wed · 3 players out",
  as_of: "2026-10-04T16:00:00Z",
  strength: 0.45,
  pre_kickoff_only: true,
  visual: "absence_strip",
};

export const PL_ABSENCE_SIGNAL: Signal = {
  kind: "absence",
  sport: "pl",
  game_id: "1",
  headline: {
    text: "Out: Saka, our #2 midfielder, 62% to score",
    figures: { projection: 62 },
  },
  n: 1,
  source: "FPL status · 1 player out",
  as_of: "2026-10-04T16:00:00Z",
  strength: 0.4,
  pre_kickoff_only: true,
  visual: "absence_strip",
};

/** A headline over the cap, for the clipped state. Its `rate` is the SAME
 *  `trustRate` as the row above: the point of the state is that clipping removes
 *  words and never a figure. */
export const LONG_HEADLINE_SIGNAL: Signal = {
  ...SIGNALS[0],
  headline: {
    text: `At ${pctWord(BUCKET.model_prob)} this model has been right ${pctWord(trustRate)} of the time across every stored pre-kickoff pick in this bucket to date.`,
    figures: SIGNALS[0].headline.figures,
  },
};

/** The same trust row with `n` under the floor — 12 games, 8 right. A state, not
 *  a second fixture: the rate and the text are derived from the same bucket. */
export const BELOW_FLOOR_SIGNAL: Signal = {
  ...SIGNALS[0],
  n: 12,
  headline: {
    text: `At ${pctWord(BUCKET.model_prob)} this model has been right ${pctWord(8 / 12)} of the time.`,
    figures: { rate: 8 / 12, model_prob: BUCKET.model_prob },
  },
};

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
  // `values` is `(number | null)[]` because `BoxScoreRow` is: a column the
  // fixture has no figure for is a null, and this guard reads only the Yds
  // figure at index 0. Typing it `number[]` would force the mock to lie about
  // the null cells to satisfy the checker, which is the opposite of a guard.
  boxRows: { key: string; values: (number | null)[] }[],
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