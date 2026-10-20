import { describe, expect, it } from "vitest";
import { SPORT_SITES, siteLinks } from "./sites";

const HOST = "40-160-91-131.sslip.io";

describe("SPORT_SITES", () => {
  it("lists the hub and the five sports in the family order", () => {
    expect(SPORT_SITES.map((s) => [s.sport, s.label])).toEqual([
      ["hub", "Home"],
      ["pl", "Premier League"],
      ["nfl", "NFL"],
      ["cfb", "College football"],
      ["nba", "NBA"],
      ["f1", "F1"],
    ]);
  });
});

describe("siteLinks", () => {
  it("keeps the current site home and sends every other site to its subdomain", () => {
    const links = siteLinks("nba", HOST);
    expect(links).toHaveLength(6);
    expect(links.find((s) => s.sport === "nba")?.href).toBe("/");
    expect(links.find((s) => s.sport === "pl")?.href).toBe(`https://pl.${HOST}`);
    expect(links.find((s) => s.sport === "nfl")?.href).toBe(`https://sports.${HOST}/?sport=nfl`);
    expect(links.find((s) => s.sport === "cfb")?.href).toBe(`https://sports.${HOST}/?sport=cfb`);
    expect(links.find((s) => s.sport === "f1")?.href).toBe(`https://f1.${HOST}`);
    expect(links.find((s) => s.sport === "hub")?.href).toBe(`https://${HOST}`);
  });

  it("uses the query form for the shared NFL/CFB app", () => {
    expect(siteLinks("nfl", HOST).find((s) => s.sport === "nfl")?.href).toBe("?sport=nfl");
    expect(siteLinks("cfb", HOST).find((s) => s.sport === "cfb")?.href).toBe("?sport=cfb");
    // The other half of the shared app is still a cross-site link.
    expect(siteLinks("nfl", HOST).find((s) => s.sport === "cfb")?.href).toBe(`https://sports.${HOST}/?sport=cfb`);
  });

  it("uses / for the current standalone site", () => {
    for (const sport of ["pl", "nba", "f1"] as const) {
      expect(siteLinks(sport, HOST).find((s) => s.sport === sport)?.href).toBe("/");
    }
  });

  it("takes the host as an argument, so a real domain is a call-site change", () => {
    const links = siteLinks("nba", "predictor.example");
    expect(links.find((s) => s.sport === "pl")?.href).toBe("https://pl.predictor.example");
    expect(links.find((s) => s.sport === "hub")?.href).toBe("https://predictor.example");
  });
});
