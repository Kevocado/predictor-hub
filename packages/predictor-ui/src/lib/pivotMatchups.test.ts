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

/** NFL three-row case (pass, rush, turnover) */
const NFL_THREE_ROWS: MatchupRow[] = [
  { id: "pass_off_vs_pass_def:home", attacker: "Bills", defender: "Jets", stat: "passing offence", foil: "pass defence", attacker_rank: 3, defender_rank: 28, n_teams: 32, toward_pick: true },
  { id: "rush_off_vs_rush_def:away", attacker: "Jets", defender: "Bills", stat: "rushing offence", foil: "run defence", attacker_rank: 4, defender_rank: 19, n_teams: 32, toward_pick: false },
  { id: "turnover_diff:home", attacker: "Bills", defender: "Jets", stat: "turnover diff", foil: "turnover diff", attacker_rank: 5, defender_rank: 20, n_teams: 32, toward_pick: null },
];

/** One-sided: only :home row */
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
    // Home always left, away always right
    expect(result!.rows[0]).toEqual({ key: "strength_attack_vs_defence_offence", label: "Attack strength", homeRank: 11, awayRank: 19, n: 20 });
    expect(result!.rows[1]).toEqual({ key: "strength_attack_vs_defence_defence", label: "Defence strength", homeRank: 16, awayRank: 3, n: 20 });
    expect(result!.rows[2]).toEqual({ key: "goals_attack_vs_defence_offence", label: "Goals scored per match", homeRank: 11, awayRank: 11, n: 20 });
    expect(result!.rows[3]).toEqual({ key: "goals_attack_vs_defence_defence", label: "Goals conceded per match", homeRank: 10, awayRank: 16, n: 20 });
    expect(result!.rows[4]).toEqual({ key: "form", label: "Recent form (points per match)", homeRank: 17, awayRank: 14, n: 20 });
  });

  it("pivots NFL three-row case (first-appearance order, offence then defence)", () => {
    const result = pivotMatchups(NFL_THREE_ROWS);
    expect(result).not.toBeNull();
    expect(result!.home).toBe("Bills");
    expect(result!.away).toBe("Jets");
    expect(result!.rows).toHaveLength(6); // pass(offence, defence), rush(offence, defence), turnover(offence, defence)

    expect(result!.rows.map(r => r.key)).toEqual([
      "pass_off_vs_pass_def_offence",
      "pass_off_vs_pass_def_defence",
      "rush_off_vs_rush_def_offence",
      "rush_off_vs_rush_def_defence",
      "turnover_diff_offence",
      "turnover_diff_defence",
    ]);
    expect(result!.rows.map(r => r.label)).toEqual([
      "Passing offence",
      "Pass defence",
      "Rushing offence",
      "Run defence",
      "Turnover diff",
      "Turnover diff",
    ]);
    // Home always left
    // pass: only :home -> offence has home rank, defence has away rank
    expect(result!.rows[0]).toEqual({ key: "pass_off_vs_pass_def_offence", label: "Passing offence", homeRank: 3, awayRank: null, n: 32 });
    expect(result!.rows[1]).toEqual({ key: "pass_off_vs_pass_def_defence", label: "Pass defence", homeRank: null, awayRank: 28, n: 32 });
    // rush: only :away (attacker Jets #4, defender Bills #19) -> away OFFENCE 4 and home DEFENCE 19; the other two
    // cells have no source row and stay empty (never borrow a rank for a different metric).
    expect(result!.rows[2]).toEqual({ key: "rush_off_vs_rush_def_offence", label: "Rushing offence", homeRank: null, awayRank: 4, n: 32 });
    expect(result!.rows[3]).toEqual({ key: "rush_off_vs_rush_def_defence", label: "Run defence", homeRank: 19, awayRank: null, n: 32 });
    // turnover: only :home -> offence has home rank, defence has away rank
    expect(result!.rows[4]).toEqual({ key: "turnover_diff_offence", label: "Turnover diff", homeRank: 5, awayRank: null, n: 32 });
    expect(result!.rows[5]).toEqual({ key: "turnover_diff_defence", label: "Turnover diff", homeRank: null, awayRank: 20, n: 32 });
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

  it("handles only :away rows (falls back to :away for team names)", () => {
    const onlyAway: MatchupRow[] = [
      { id: "pass_off_vs_pass_def:away", attacker: "Jets", defender: "Bills", stat: "passing offence", foil: "pass defence", attacker_rank: 4, defender_rank: 19, n_teams: 32, toward_pick: false },
    ];
    const result = pivotMatchups(onlyAway);
    expect(result).not.toBeNull();
    expect(result!.home).toBe("Bills");
    expect(result!.away).toBe("Jets");
    expect(result!.rows).toHaveLength(2);
    // Jets (away) attack #4 -> away offence 4; Bills (home) defence #19 -> home defence 19. Nothing else is known.
    expect(result!.rows[0]).toEqual({ key: "pass_off_vs_pass_def_offence", label: "Passing offence", homeRank: null, awayRank: 4, n: 32 });
    expect(result!.rows[1]).toEqual({ key: "pass_off_vs_pass_def_defence", label: "Pass defence", homeRank: 19, awayRank: null, n: 32 });
  });
});