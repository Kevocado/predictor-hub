import { describe, expect, it } from "vitest";
import { pivotMatchups } from "./pivotMatchups";
import type { MatchupRow } from "../components/MatchupBrief";

const FIVE_PL_ROWS: MatchupRow[] = [
  { id: "goals_scored_per_match:home", attacker: "Arsenal", defender: "Chelsea", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 3, defender_rank: 12, n_teams: 20, toward_pick: true },
  { id: "goals_conceded_per_match:away", attacker: "Chelsea", defender: "Arsenal", stat: "goals conceded per match", foil: "goals scored per match", attacker_rank: 5, defender_rank: 2, n_teams: 20, toward_pick: false },
  { id: "shots_on_target_per_match:home", attacker: "Arsenal", defender: "Chelsea", stat: "shots on target per match", foil: "shots on target faced per match", attacker_rank: 4, defender_rank: 15, n_teams: 20, toward_pick: null },
  { id: "shots_on_target_faced_per_match:away", attacker: "Chelsea", defender: "Arsenal", stat: "shots on target faced per match", foil: "shots on target per match", attacker_rank: 8, defender_rank: 6, n_teams: 20, toward_pick: null },
  { id: "possession_pct:home", attacker: "Arsenal", defender: "Chelsea", stat: "possession %", foil: "possession %", attacker_rank: 2, defender_rank: 10, n_teams: 20, toward_pick: true },
];

const NFL_THREE_ROWS: MatchupRow[] = [
  { id: "pass_off_vs_pass_def:home", attacker: "Bills", defender: "Jets", stat: "passing offence", foil: "pass defence", attacker_rank: 3, defender_rank: 28, n_teams: 32, toward_pick: true },
  { id: "rush_off_vs_rush_def:away", attacker: "Jets", defender: "Bills", stat: "rushing offence", foil: "run defence", attacker_rank: 4, defender_rank: 19, n_teams: 32, toward_pick: false },
  { id: "turnover_diff:home", attacker: "Bills", defender: "Jets", stat: "turnover diff", foil: "turnover diff", attacker_rank: 5, defender_rank: 20, n_teams: 32, toward_pick: null },
];

const ONE_SIDED_ONLY_HOME: MatchupRow[] = [
  { id: "goals_scored_per_match:home", attacker: "Arsenal", defender: "Chelsea", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 3, defender_rank: 12, n_teams: 20, toward_pick: true },
];

const MALFORMED_ROWS: MatchupRow[] = [
  { id: "valid:home", attacker: "Arsenal", defender: "Chelsea", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 3, defender_rank: 12, n_teams: 20, toward_pick: true },
  { id: "", attacker: "Arsenal", defender: "Chelsea", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 3, defender_rank: 12, n_teams: 20, toward_pick: true },
  { id: "bad_rank", attacker: "Arsenal", defender: "Chelsea", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 25, defender_rank: 12, n_teams: 20, toward_pick: true },
];

describe("pivotMatchups", () => {
  it("pivots the five live PL rows into the expected table shape (alphabetical by key)", () => {
    const result = pivotMatchups(FIVE_PL_ROWS);
    expect(result).not.toBeNull();
    expect(result!.home).toBe("Arsenal");
    expect(result!.away).toBe("Chelsea");
    expect(result!.rows).toHaveLength(5);
    // Row order: alphabetical by key
    expect(result!.rows.map(r => r.key)).toEqual([
      "goals_conceded_per_match",
      "goals_scored_per_match",
      "possession_pct",
      "shots_on_target_faced_per_match",
      "shots_on_target_per_match",
    ]);
    expect(result!.rows.map(r => r.label)).toEqual([
      "Goals conceded per match",
      "Goals scored per match",
      "Possession %",
      "Shots on target faced per match",
      "Shots on target per match",
    ]);
    // Home always left, away always right
    expect(result!.rows[0]).toEqual({ key: "goals_conceded_per_match", label: "Goals conceded per match", homeRank: 2, awayRank: 5, n: 20 });
    expect(result!.rows[1]).toEqual({ key: "goals_scored_per_match", label: "Goals scored per match", homeRank: 3, awayRank: 12, n: 20 });
    expect(result!.rows[2]).toEqual({ key: "possession_pct", label: "Possession %", homeRank: 2, awayRank: 10, n: 20 });
    expect(result!.rows[3]).toEqual({ key: "shots_on_target_faced_per_match", label: "Shots on target faced per match", homeRank: 6, awayRank: 8, n: 20 });
    expect(result!.rows[4]).toEqual({ key: "shots_on_target_per_match", label: "Shots on target per match", homeRank: 4, awayRank: 15, n: 20 });
  });

  it("pivots NFL three-row case (alphabetical by key)", () => {
    const result = pivotMatchups(NFL_THREE_ROWS);
    expect(result).not.toBeNull();
    expect(result!.home).toBe("Bills");
    expect(result!.away).toBe("Jets");
    expect(result!.rows).toHaveLength(3);
    expect(result!.rows.map(r => r.key)).toEqual([
      "pass_off_vs_pass_def",
      "rush_off_vs_rush_def",
      "turnover_diff",
    ]);
    expect(result!.rows.map(r => r.label)).toEqual([
      "Pass off vs pass def",
      "Rush off vs rush def",
      "Turnover diff",
    ]);
    // Home always left
    expect(result!.rows[0]).toEqual({ key: "pass_off_vs_pass_def", label: "Pass off vs pass def", homeRank: 3, awayRank: 28, n: 32 });
    expect(result!.rows[1]).toEqual({ key: "rush_off_vs_rush_def", label: "Rush off vs rush def", homeRank: 19, awayRank: 4, n: 32 });
    expect(result!.rows[2]).toEqual({ key: "turnover_diff", label: "Turnover diff", homeRank: 5, awayRank: 20, n: 32 });
  });

  it("one-sided case (only :home row) still has both ranks from that row", () => {
    const result = pivotMatchups(ONE_SIDED_ONLY_HOME);
    expect(result).not.toBeNull();
    expect(result!.rows).toHaveLength(1);
    // The :home row contains both home's stat rank (attacker_rank) and away's foil rank (defender_rank)
    expect(result!.rows[0]).toEqual({
      key: "goals_scored_per_match",
      label: "Goals scored per match",
      homeRank: 3,
      awayRank: 12,
      n: 20,
    });
  });

  it("drops malformed rows", () => {
    const result = pivotMatchups(MALFORMED_ROWS);
    expect(result).not.toBeNull();
    expect(result!.rows).toHaveLength(1);
    expect(result!.rows[0].key).toBe("valid");
  });

  it("empty input returns null", () => {
    expect(pivotMatchups([])).toBeNull();
  });

  it("row order shuffled gives the same table (alphabetical by key)", () => {
    const shuffled = [...FIVE_PL_ROWS].sort(() => Math.random() - 0.5);
    const result = pivotMatchups(shuffled);
    const ordered = pivotMatchups(FIVE_PL_ROWS);
    expect(result).toEqual(ordered);
  });

  it("returns null when nothing drawable after filtering", () => {
    const allBad: MatchupRow[] = [
      { id: "bad_rank", attacker: "Arsenal", defender: "Chelsea", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 25, defender_rank: 12, n_teams: 20, toward_pick: true },
      { id: "bad_n", attacker: "Arsenal", defender: "Chelsea", stat: "goals scored per match", foil: "goals conceded per match", attacker_rank: 3, defender_rank: 12, n_teams: 1, toward_pick: true },
    ];
    expect(pivotMatchups(allBad)).toBeNull();
  });
});