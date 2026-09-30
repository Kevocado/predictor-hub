import { describe, expect, it } from "vitest";
import { pickLabel, pickProbability, pickTiming, verdictSentence } from "./bundleFacts";

// The Sports bundle carries the abbreviation everywhere it is joined on
// (`home_team`, `pick.label`, a segment's `label`) and the long name beside it,
// so `home_team_full` is here for the same reason the InstantBlock fixture
// carries it: the verdict expands only when the bundle itself has the full name.
// Nothing in the package invents one from a table.
const PL = { team_home: "Arsenal", team_away: "Chelsea", home_win_prob: 0.57, away_win_prob: 0.2, pick: "Arsenal" };
const NFL = { home_team: "GB", home_team_full: "Green Bay", away_team: "ATL", home_win_prob: 0.72, away_win_prob: 0.28, pick: { label: "GB", prob: 0.72 } };
const NBA_REBUILT = { home_team: "BOS", away_team: "MIA", pick: { label: "BOS", prob: 0.64 }, pick_timing: "rebuilt" };
// F1's honest answer when the schedule carries no session start is the word
// `"unknown"` — the service's `PickTiming` literal (services/explainer/
// explainer/facts.py:25) and what F1_Predictor#16 sends. `session_start: null`
// is the fact underneath it, kept here so the fixture reads as what it is.
const F1_UNKNOWN = { driver: "Max Verstappen", pick: "Max Verstappen", pick_timing: "unknown", session_start: null };

describe("pickLabel", () => {
  it("reads a Sports-style object pick", () => { expect(pickLabel(NFL, "nfl")).toBe("GB"); });
  it("reads a PL string pick", () => { expect(pickLabel(PL, "pl")).toBe("Arsenal"); });
  it("reads an F1 driver pick", () => { expect(pickLabel(F1_UNKNOWN, "f1")).toBe("Max Verstappen"); });
  it("is null when the bundle names no pick", () => { expect(pickLabel({ home_team: "GB" }, "nfl")).toBeNull(); });
});

describe("pickProbability", () => {
  it("prefers the pick's own probability", () => { expect(pickProbability(NFL)).toBe(0.72); });
  it("returns null rather than guessing from a team's win probability", () => {
    // PL's bundle carries the prob on the pick, not on the sides.
    expect(pickProbability({ team_home: "Arsenal", pick: "Arsenal" })).toBeNull();
  });
});

describe("pickTiming", () => {
  it("reports a rebuilt pick, in the sport's own moment", () => {
    expect(pickTiming(NBA_REBUILT, "nba")).toEqual({ status: "rebuilt", moment: "tip-off" });
  });
  it("reports unverified for F1 when the schedule gave no start time", () => {
    expect(pickTiming(F1_UNKNOWN, "f1")).toEqual({ status: "unverified", moment: "the session" });
  });
  it("reports nopick when the bundle names no pick", () => {
    expect(pickTiming({ home_team: "GB", away_team: "ATL" }, "nfl")).toEqual({ status: "nopick", moment: "kickoff" });
  });
  it("reports none for a pick made before the start", () => {
    expect(pickTiming(NFL, "nfl")).toEqual({ status: "none", moment: "kickoff" });
  });
});

describe("verdictSentence", () => {
  it("states the pick and nothing else", () => {
    expect(verdictSentence(NFL, "nfl")).toBe("Green Bay is the pick.");
  });
  it("is null when there is no pick, so the block says nothing", () => {
    expect(verdictSentence({ home_team: "GB" }, "nfl")).toBeNull();
  });
});