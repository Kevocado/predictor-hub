import { describe, expect, it } from "vitest";
import { kickoff, margin, modelDate, parseKickoff, pct, pctFine, record, signed, spread, stat, streak } from "./fmt";

describe("pct", () => {
  it("rounds to whole percents", () => {
    expect(pct(0.47)).toBe("47%");
    expect(pct(0.535)).toBe("54%");
  });
  it("never prints 0% or 100% for a live probability", () => {
    expect(pct(0.004)).toBe("<1%");
    expect(pct(0)).toBe("<1%");
    expect(pct(0.005)).toBe("<1%");
    expect(pct(0.996)).toBe(">99%");
    expect(pct(0.995)).toBe(">99%");
    expect(pct(1)).toBe(">99%");
  });
  it("prints a dash for missing values", () => {
    expect(pct(Number.NaN)).toBe("—");
  });
});

describe("pctFine", () => {
  it("uses one decimal under 10% and whole percents above", () => {
    expect(pctFine(0.064)).toBe("6.4%");
    expect(pctFine(0.178)).toBe("18%");
    expect(pctFine(0.0004)).toBe("<0.1%");
  });
});

describe("stat, signed, streak, record", () => {
  it("stat keeps one decimal", () => {
    expect(stat(16.514463424682617)).toBe("16.5");
    expect(stat(Number.NaN)).toBe("—");
  });
  it("signed always shows a sign and uses a true minus", () => {
    expect(signed(1.5)).toBe("+1.5");
    expect(signed(-1.5)).toBe("−1.5");
    expect(signed(0)).toBe("0.0");
  });
  it("streak reads W/L", () => {
    expect(streak(-1)).toBe("L1");
    expect(streak(3)).toBe("W3");
    expect(streak(0)).toBe("—");
  });
  it("record reads hits/settled", () => {
    expect(record(4, 7)).toBe("4/7");
    expect(record(0, 0)).toBe("—");
  });
});

describe("margin and spread", () => {
  it("margin names the team and hides tiny or missing margins", () => {
    // x is home minus away: its sign picks the favoured team.
    expect(margin("TOR", "MIA", -4.8)).toBe("MIA by 4.8");
    expect(margin("TOR", "MIA", 4.8)).toBe("TOR by 4.8");
    expect(margin("TOR", "MIA", 0.3)).toBe("Toss-up");
    expect(margin("TOR", "MIA", -0)).toBe("Toss-up");
    expect(margin("TOR", "MIA", Number.NaN)).toBe("Toss-up");
  });
  it("spread writes the line with its team", () => {
    expect(spread("KC", -3.5)).toBe("KC −3.5");
    expect(spread("KC", 3)).toBe("KC +3");
    expect(spread("KC", 0)).toBe("KC PK");
    expect(spread("KC", -0)).toBe("KC PK");
    expect(spread("KC", Number.NaN)).toBe("—");
  });
});

describe("kickoff", () => {
  it("always shows the zone", () => {
    expect(kickoff("2026-10-04T00:30:00Z", "America/Chicago")).toBe("Sat 3 Oct · 7:30 PM CDT");
  });
  it("falls back to an offset where the zone has no short name", () => {
    expect(kickoff("2026-10-04T00:30:00Z", "Asia/Dubai")).toMatch(/^Sun 4 Oct · 4:30 AM GMT\+4$/);
  });
  it("prints a dash for an invalid date", () => {
    expect(kickoff("not a date")).toBe("—");
  });
});

describe("modelDate", () => {
  it("turns a version id into a plain date", () => {
    expect(modelDate("v20260918120240")).toBe("Sep 18 model");
    expect(modelDate("2026-09-18T12:02:40.134071+00:00")).toBe("Sep 18 model");
    expect(modelDate("garbage")).toBe("Model");
  });
});

describe("review fixes", () => {
  it("uses a true minus in stat and rounds before choosing a sign", () => {
    expect(stat(-3.2)).toBe("\u22123.2");
    expect(signed(-0.04)).toBe("0.0");
    expect(signed(0.04)).toBe("0.0");
  });
  it("treats Infinity like missing data", () => {
    expect(stat(Infinity)).toBe("—");
    expect(signed(-Infinity)).toBe("—");
    expect(spread("KC", Infinity)).toBe("—");
    expect(record(Number.NaN, 7)).toBe("—");
    expect(streak(2.5)).toBe("—");
  });
  it("pctFine never prints 10.0%", () => {
    expect(pctFine(0.0995)).toBe("10%");
    expect(pctFine(0.09999)).toBe("10%");
  });
  it("kickoff survives a bad zone and treats a bare date as a date", () => {
    expect(kickoff("2026-10-04T00:30:00Z", "Not/AZone")).not.toBe("—");
    expect(kickoff("2026-10-04")).toBe("Sun 4 Oct");
  });
  it("modelDate rejects impossible dates", () => {
    expect(modelDate("v20261399")).toBe("Model");
    expect(modelDate("1")).toBe("Model");
  });
});

describe("zoneless timestamps (the NFL API sends '2026-10-04T17:00:00')", () => {
  it("parseKickoff reads a date-time without a zone as UTC", () => {
    expect(parseKickoff("2026-10-04T17:00:00").toISOString()).toBe("2026-10-04T17:00:00.000Z");
    expect(parseKickoff("2026-10-04T17:00:00Z").toISOString()).toBe("2026-10-04T17:00:00.000Z");
    expect(parseKickoff("2026-10-04T12:00:00-05:00").toISOString()).toBe("2026-10-04T17:00:00.000Z");
  });
  it("kickoff shows a 1pm ET kickoff at noon Central, not 5 PM", () => {
    expect(kickoff("2026-10-04T17:00:00", "America/Chicago")).toBe("Sun 4 Oct · 12:00 PM CDT");
  });
});
