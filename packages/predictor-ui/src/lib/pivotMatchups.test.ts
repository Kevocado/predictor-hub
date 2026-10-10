import { describe, expect, it } from "vitest";
import { pivotMatchups } from "./pivotMatchups";
import type { MatchupRow } from "../components/MatchupBrief";

/** Live PL rows from the plan (Bournemouth v Sunderland, event ockw-Aksg-QRth) */
const PL_LIVE_ROWS: MatchupRow[] = [
  { id: "strength_attack_vs_defence:home", attacker: "Bournemouth", defender: "Sunderland", stat: "attack strength", foil: "defence strength", attacker_rank: 11, defender_rank: 3, n_teams: 20, toward_pick: null },
  { id: "goals_attack_vs_defence:home", attacker: "Bournemouth", defender: "Sunderland", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 11, defender_rank: 16, n_teams: 20, toward_pick: null },
  { id: "strength_attack_vs_defence:away", attacker: "Sunderland", defender: "Bournemouth", stat: "attack strength", foil: "defence strength", attacker_rank: 19, defender_rank: 16, n_teams: 20, toward_pick: null },
  { id: "form", attacker: "Bournemouth", defender: "Sunderland", stat: "recent form (points per match)", foil: "recent form (points per match)", attacker_rank: 17, defender_rank: 14, n_teams: 20, toward_pick: null },
  { id: "goals_attack_vs_defence:away", attacker: "Sunderland", defender: "Bournemouth", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 11, defender_rank: 10, n_teams: 20, toward_pick: null },
];

/** NFL rows with real ids (both sides for pass and rush, n=32) */
const NFL_REAL_ROWS: MatchupRow[] = [
  { id: "pass_off_vs_pass_def:home", attacker: "Bills", defender: "Jets", stat: "passing offence", foil: "pass defence", attacker_rank: 3, defender_rank: 28, n_teams: 32, toward_pick: true },
  { id: "pass_off_vs_pass_def:away", attacker: "Jets", defender: "Bills", stat: "passing offence", foil: "pass defence", attacker_rank: 28, defender_rank: 3, n_teams: 32, toward_pick: false },
  { id: "rush_off_vs_rush_def:home", attacker: "Bills", defender: "Jets", stat: "rushing offence", foil: "run defence", attacker_rank: 12, defender_rank: 19, n_teams: 32, toward_pick: true },
  { id: "rush_off_vs_rush_def:away", attacker: "Jets", defender: "Bills", stat: "rushing offence", foil: "run defence", attacker_rank: 19, defender_rank: 12, n_teams: 32, toward_pick: false },
];

/** One-sided: only :home row — genuinely missing away defender rank (null) */
const ONE_SIDED_ONLY_HOME: MatchupRow[] = [
  { id: "goals_scored_per_match:home", attacker: "Arsenal", defender: "Chelsea", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 3, defender_rank: 12, n_teams: 20, toward_pick: true },
];

/** Malformed rows mixed with valid */
const MALFORMED_ROWS: MatchupRow[] = [
  { id: "valid:home", attacker: "Arsenal", defender: "Chelsea", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 3, defender_rank: 12, n_teams: 20, toward_pick: true },
  { id: "", attacker: "Arsenal", defender: "Chelsea", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 3, defender_rank: 12, n_teams: 20, toward_pick: true },
  { id: "bad_rank", attacker: "Arsenal", defender: "Chelsea", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 25, defender_rank: 12, n_teams: 20, toward_pick: true },
];

describe("pivotMatchups", () => {
  it("pivots the five live PL rows into the expected table shape (first-appearance order, offence then defence, unsuffixed last)", () => {
    const result = pivotMatchups(PL_LIVE_ROWS);
    expect(result).not.toBeNull();
    expect(result!.home).toBe("Bournemouth");
    expect(result!.away).toBe("Sunderland");
    expect(result!.rows).toHaveLength(5);

    // Row order: strength (offence, defence), goals (offence, defence), form (unsuffixed)
    expect(result!.rows.map(r => r.key)).toEqual([
      "strength_attack_vs_defence_offence",
      "strength_attack_vs_defence_defence",
      "goals_attack_vs_defence_offence",
      "goals_attack_vs_defence_defence",
      "form",
    ]);
    expect(result!.rows.map(r => r.label)).toEqual([
      "Attack strength",
      "Defence strength",
      "Goals scored per match",
      "Goals conceded per match",
      "Recent form (points per match)",
    ]);
    // Home always left, away always right — matches plan's expected table
    expect(result!.rows[0]).toEqual({ key: "strength_attack_vs_defence_offence", label: "Attack strength", homeRank: 11, awayRank: 19, n: 20 });
    expect(result!.rows[1]).toEqual({ key: "strength_attack_vs_defence_defence", label: "Defence strength", homeRank: 16, awayRank: 3, n: 20 });
    expect(result!.rows[2]).toEqual({ key: "goals_attack_vs_defence_offence", label: "Goals scored per match", homeRank: 11, awayRank: 11, n: 20 });
    expect(result!.rows[3]).toEqual({ key: "goals_attack_vs_defence_defence", label: "Goals conceded per match", homeRank: 10, awayRank: 16, n: 20 });
    expect(result!.rows[4]).toEqual({ key: "form", label: "Recent form (points per match)", homeRank: 17, awayRank: 14, n: 20 });
  });

  it("pivots NFL real-id rows (first-appearance order, offence then defence)", () => {
    const result = pivotMatchups(NFL_REAL_ROWS);
    expect(result).not.toBeNull();
    expect(result!.home).toBe("Bills");
    expect(result!.away).toBe("Jets");
    expect(result!.rows).toHaveLength(4);

    expect(result!.rows.map(r => r.key)).toEqual([
      "pass_off_vs_pass_def_offence",
      "pass_off_vs_pass_def_defence",
      "rush_off_vs_rush_def_offence",
      "rush_off_vs_rush_def_defence",
    ]);
    expect(result!.rows.map(r => r.label)).toEqual([
      "Passing offence",
      "Pass defence",
      "Rushing offence",
      "Run defence",
    ]);
    // Home always left
    expect(result!.rows[0]).toEqual({ key: "pass_off_vs_pass_def_offence", label: "Passing offence", homeRank: 3, awayRank: 28, n: 32 });
    expect(result!.rows[1]).toEqual({ key: "pass_off_vs_pass_def_defence", label: "Pass defence", homeRank: 3, awayRank: 28, n: 32 });
    expect(result!.rows[2]).toEqual({ key: "rush_off_vs_rush_def_offence", label: "Rushing offence", homeRank: 12, awayRank: 19, n: 32 });
    expect(result!.rows[3]).toEqual({ key: "rush_off_vs_rush_def_defence", label: "Run defence", homeRank: 12, awayRank: 19, n: 32 });
  });

  it("one-sided case (only :home row) produces offence and defence rows with null on missing side", () => {
    const result = pivotMatchups(ONE_SIDED_ONLY_HOME);
    expect(result).not.toBeNull();
    expect(result!.rows).toHaveLength(2);
    // Offence: home has stat rank, away null
    expect(result!.rows[0]).toEqual({
      key: "goals_scored_per_match_offence",
      label: "Goals scored per match",
      homeRank: 3,
      awayRank: null,
      n: 20,
    });
    // Defence: home null, away has foil rank
    expect(result!.rows[1]).toEqual({
      key: "goals_scored_per_match_defence",
      label: "Goals conceded per match",
      homeRank: null,
      awayRank: 12,
      n: 20,
    });
  });

  it(":away-only row — offence away has rank, home null; defence home has rank, away null", () => {
    const onlyAway: MatchupRow[] = [
      { id: "pass_off_vs_pass_def:away", attacker: "Jets", defender: "Bills", stat: "passing offence", foil: "pass defence", attacker_rank: 4, defender_rank: 19, n_teams: 32, toward_pick: false },
    ];
    const result = pivotMatchups(onlyAway);
    expect(result).not.toBeNull();
    expect(result!.home).toBe("Bills");
    expect(result!.away).toBe("Jets");
    expect(result!.rows).toHaveLength(2);
    // Offence: home null, away has attacker_rank
    expect(result!.rows[0]).toEqual({ key: "pass_off_vs_pass_def_offence", label: "Passing offence", homeRank: null, awayRank: 4, n: 32 });
    // Defence: home has defender_rank, away null
    expect(result!.rows[1]).toEqual({ key: "pass_off_vs_pass_def_defence", label: "Pass defence", homeRank: 19, awayRank: null, n: 32 });
  });

  it("drops malformed rows", () => {
    const result = pivotMatchups(MALFORMED_ROWS);
    expect(result).not.toBeNull();
    expect(result!.rows).toHaveLength(2); // valid:home produces offence + defence
    expect(result!.rows[0].key).toBe("valid_offence");
    expect(result!.rows[1].key).toBe("valid_defence");
  });

  it("empty input returns null", () => {
    expect(pivotMatchups([])).toBeNull();
  });

  it("same input gives same output (deterministic)", () => {
    const result1 = pivotMatchups(PL_LIVE_ROWS);
    const result2 = pivotMatchups(PL_LIVE_ROWS);
    expect(result1).toEqual(result2);
  });

  it("returns null when nothing drawable after filtering", () => {
    const allBad: MatchupRow[] = [
      { id: "bad_rank", attacker: "Arsenal", defender: "Chelsea", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 25, defender_rank: 12, n_teams: 20, toward_pick: true },
      { id: "bad_n", attacker: "Arsenal", defender: "Chelsea", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 3, defender_rank: 12, n_teams: 1, toward_pick: true },
    ];
    expect(pivotMatchups(allBad)).toBeNull();
  });
});